// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

//! Redfish event listener — embedded HTTP(S) server that receives push events.
//!
//! Design §15: `RedfishEventListener` spins up an axum server on a
//! caller-chosen port.  Features:
//!
//! * **Context-token validation** (FR5.3) — returns 204 No Content on mismatch
//!   so as not to reveal configuration to unknown senders.
//! * **Ring buffer** — last 500 events kept in memory for inspection.
//! * **Per-IP counter** — tracked via `ConnectInfo<SocketAddr>`.
//! * **Latency logging** — arrival-to-dispatch wall time via `tracing::debug!`.
//! * **Typed callbacks** — register async closures by registry prefix, event
//!   type string, or catch-all.

use std::{
    collections::{HashMap, VecDeque},
    net::SocketAddr,
    sync::Arc,
    time::Instant,
};

use axum::{
    extract::{ConnectInfo, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize}; // needed for derive expansions in this file
use serde_json::Value;
use tokio::{
    sync::Mutex,
    task::JoinHandle,
};
use tracing::{debug, warn};

// ─── Event payload ────────────────────────────────────────────────────────────

/// A single Redfish event object received from a BMC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RedfishEvent {
    /// The `EventType` field from the payload.
    #[serde(rename = "EventType", default)]
    pub event_type: String,
    /// The `EventId` field from the payload.
    #[serde(rename = "EventId", default)]
    pub event_id: String,
    /// The `EventTimestamp` field from the payload.
    #[serde(rename = "EventTimestamp", default)]
    pub timestamp: String,
    /// The `Severity` field from the payload.
    #[serde(rename = "Severity", default)]
    pub severity: String,
    /// The `Message` field from the payload.
    #[serde(rename = "Message", default)]
    pub message: String,
    /// The `MessageId` field from the payload (e.g. `"Base.1.0.Success"`).
    #[serde(rename = "MessageId", default)]
    pub message_id: String,
    /// The `OriginOfCondition` object (resource URI).
    #[serde(rename = "OriginOfCondition", default)]
    pub origin_of_condition: Option<Value>,
    /// Full raw payload kept for callers who need non-standard fields.
    #[serde(rename = "_raw", default)]
    pub raw: Option<Value>,
}

/// The top-level POST body sent by the BMC.
#[derive(Debug, Deserialize)]
struct EventPostBody {
    /// Optional context token echoed back by the BMC.
    #[serde(rename = "Context", default)]
    context: Option<String>,
    /// The array of event objects.
    #[serde(rename = "Events", default)]
    events: Vec<Value>,
}

// ─── Callback registry ────────────────────────────────────────────────────────

type BoxedCallback = Box<dyn Fn(RedfishEvent) + Send + Sync + 'static>;

#[derive(Default)]
struct CallbackRegistry {
    /// Catch-all callbacks — invoked for every event.
    any: Vec<BoxedCallback>,
    /// Callbacks keyed by exact `EventType` string.
    by_type: HashMap<String, Vec<BoxedCallback>>,
    /// Callbacks keyed by registry prefix (first component of `MessageId`).
    by_registry: HashMap<String, Vec<BoxedCallback>>,
}

impl CallbackRegistry {
    fn dispatch(&self, event: &RedfishEvent) {
        for cb in &self.any {
            cb(event.clone());
        }
        if !event.event_type.is_empty() {
            if let Some(cbs) = self.by_type.get(&event.event_type) {
                for cb in cbs {
                    cb(event.clone());
                }
            }
        }
        if let Some(prefix) = event.message_id.split('.').next() {
            if let Some(cbs) = self.by_registry.get(prefix) {
                for cb in cbs {
                    cb(event.clone());
                }
            }
        }
    }
}

// ─── Shared server state ──────────────────────────────────────────────────────

struct ListenerState {
    context_token: Option<String>,
    callbacks:     std::sync::Mutex<CallbackRegistry>,
    event_buffer:  Mutex<VecDeque<RedfishEvent>>,
    ip_stats:      Mutex<HashMap<String, u64>>,
}

// ─── Listener struct ──────────────────────────────────────────────────────────

/// An embedded HTTP server that receives Redfish push-event notifications.
///
/// # Example
/// ```no_run
/// # use redfish_sdk::events::RedfishEventListener;
/// # #[tokio::main] async fn main() {
/// let mut listener = RedfishEventListener::new(8443)
///     .with_context_token("my-secret-token");
/// listener.on_event(|ev| {
///     println!("Got event: {}", ev.message);
/// });
/// listener.start().await.unwrap();
/// # }
/// ```
pub struct RedfishEventListener {
    port: u16,
    host: String,
    context_token: Option<String>,
    state: Arc<ListenerState>,
    join_handle: Option<JoinHandle<()>>,
}

impl RedfishEventListener {
    /// Create a listener on the given TCP port, binding to `0.0.0.0`.
    pub fn new(port: u16) -> Self {
        Self::with_host("0.0.0.0", port)
    }

    /// Create a listener binding to a specific host/IP address.
    pub fn with_host(host: impl Into<String>, port: u16) -> Self {
        let host = host.into();
        let state = Arc::new(ListenerState {
            context_token: None,
            callbacks:     std::sync::Mutex::new(CallbackRegistry::default()),
            event_buffer:  Mutex::new(VecDeque::with_capacity(500)),
            ip_stats:      Mutex::new(HashMap::new()),
        });
        Self {
            port,
            host,
            context_token: None,
            state,
            join_handle: None,
        }
    }

    /// Require the BMC to echo this context token in every POST.
    ///
    /// Requests that do not match return HTTP 204 silently (FR5.3).
    pub fn with_context_token(mut self, token: impl Into<String>) -> Self {
        self.context_token = Some(token.into());
        self
    }

    // ── Callback registration ─────────────────────────────────────────────

    /// Register a synchronous catch-all callback invoked for every event.
    pub fn on_event<F>(&self, callback: F)
    where
        F: Fn(RedfishEvent) + Send + Sync + 'static,
    {
        self.state.callbacks.lock().unwrap().any.push(Box::new(callback));
    }

    /// Register a callback for a specific `EventType` string
    /// (e.g. `"Alert"`, `"ResourceAdded"`).
    pub fn on_event_type<F>(&self, event_type: impl Into<String>, callback: F)
    where
        F: Fn(RedfishEvent) + Send + Sync + 'static,
    {
        let event_type = event_type.into();
        self.state.callbacks.lock().unwrap()
            .by_type
            .entry(event_type)
            .or_default()
            .push(Box::new(callback));
    }

    /// Register a callback for a specific message-registry prefix
    /// (e.g. `"Base"` matches `"Base.1.0.Success"`).
    pub fn on_registry<F>(&self, registry_prefix: impl Into<String>, callback: F)
    where
        F: Fn(RedfishEvent) + Send + Sync + 'static,
    {
        let prefix = registry_prefix.into();
        self.state.callbacks.lock().unwrap()
            .by_registry
            .entry(prefix)
            .or_default()
            .push(Box::new(callback));
    }

    // ── Lifecycle ────────────────────────────────────────────────────────

    /// Start the listener server in a background tokio task.
    ///
    /// Returns immediately; the server runs until [`stop()`] is called or this
    /// struct is dropped.
    pub async fn start(&mut self) -> Result<(), crate::RedfishError> {
        if self.join_handle.is_some() {
            return Ok(()); // already running
        }

        // Rebuild shared state with the (possibly updated) context token.
        let callbacks_snapshot = std::mem::take(
            &mut *self.state.callbacks.lock().unwrap(),
        );
        let state = Arc::new(ListenerState {
            context_token: self.context_token.clone(),
            callbacks:     std::sync::Mutex::new(callbacks_snapshot),
            event_buffer:  Mutex::new(VecDeque::with_capacity(500)),
            ip_stats:      Mutex::new(HashMap::new()),
        });
        self.state = Arc::clone(&state);

        let addr: SocketAddr = format!("{}:{}", self.host, self.port)
            .parse()
            .map_err(|e: std::net::AddrParseError| {
                crate::RedfishError::ProtocolError(e.to_string())
            })?;

        let router = Router::new()
            .route("/", post(handle_post))
            .with_state(Arc::clone(&state))
            .into_make_service_with_connect_info::<SocketAddr>();

        let listener = tokio::net::TcpListener::bind(addr)
            .await
            .map_err(|e| crate::RedfishError::ConnectionFailed(e.to_string()))?;

        let handle = tokio::spawn(async move {
            if let Err(e) = axum::serve(listener, router).await {
                warn!("Event listener server exited: {e}");
            }
        });

        self.join_handle = Some(handle);
        Ok(())
    }

    /// Stop the background server task.
    pub async fn stop(&mut self) {
        if let Some(h) = self.join_handle.take() {
            h.abort();
            let _ = h.await;
        }
    }

    // ── Inspection ───────────────────────────────────────────────────────

    /// Return a snapshot of the ring buffer (up to 500 most recent events).
    pub async fn get_buffered_events(&self) -> Vec<RedfishEvent> {
        self.state.event_buffer.lock().await.iter().cloned().collect()
    }

    /// Return a copy of per-source-IP POST counts.
    pub async fn get_ip_stats(&self) -> HashMap<String, u64> {
        self.state.ip_stats.lock().await.clone()
    }

    /// Synchronous version of [`get_buffered_events`].
    pub fn get_buffered_events_blocking(&self) -> Vec<RedfishEvent> {
        self.state
            .event_buffer
            .blocking_lock()
            .iter()
            .cloned()
            .collect()
    }

    /// Synchronous version of [`get_ip_stats`].
    pub fn get_ip_stats_blocking(&self) -> HashMap<String, u64> {
        self.state.ip_stats.blocking_lock().clone()
    }
}

impl Drop for RedfishEventListener {
    fn drop(&mut self) {
        if let Some(h) = self.join_handle.take() {
            h.abort();
        }
    }
}

// ─── axum handler ─────────────────────────────────────────────────────────────

async fn handle_post(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<Arc<ListenerState>>,
    Json(body): Json<EventPostBody>,
) -> StatusCode {
    let arrival = Instant::now();
    let ip = addr.ip().to_string();

    // FR5.3 — context-token validation
    if let Some(expected) = &state.context_token {
        if body.context.as_deref() != Some(expected.as_str()) {
            debug!(ip = %ip, "context-token mismatch — dropping silently");
            return StatusCode::NO_CONTENT;
        }
    }

    // Per-IP counter
    {
        let mut stats = state.ip_stats.lock().await;
        *stats.entry(ip.clone()).or_insert(0) += 1;
    }

    // Parse each event object
    let mut parsed_events: Vec<RedfishEvent> = Vec::new();
    for raw_val in &body.events {
        let mut ev: RedfishEvent = match serde_json::from_value(raw_val.clone()) {
            Ok(e) => e,
            Err(err) => {
                warn!(ip = %ip, "failed to parse event object: {err}");
                continue;
            }
        };
        ev.raw = Some(raw_val.clone());
        parsed_events.push(ev);
    }

    // Ring buffer (cap 500)
    {
        let mut buf = state.event_buffer.lock().await;
        for ev in &parsed_events {
            if buf.len() >= 500 {
                buf.pop_front();
            }
            buf.push_back(ev.clone());
        }
    }

    // Dispatch callbacks
    let callbacks = state.callbacks.lock().unwrap();
    for ev in &parsed_events {
        callbacks.dispatch(ev);
    }

    let latency = arrival.elapsed();
    debug!(
        ip      = %ip,
        events  = parsed_events.len(),
        latency = ?latency,
        "events dispatched"
    );

    StatusCode::OK
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_event(event_type: &str, message_id: &str) -> RedfishEvent {
        RedfishEvent {
            event_type: event_type.to_string(),
            event_id: "1".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            severity: "OK".to_string(),
            message: "test".to_string(),
            message_id: message_id.to_string(),
            origin_of_condition: None,
            raw: None,
        }
    }

    #[test]
    fn test_callback_registry_dispatch() {
        let reg = CallbackRegistry::default();
        let ev = sample_event("Alert", "Base.1.0.Success");
        // Should not panic with no callbacks registered.
        reg.dispatch(&ev);
    }

    #[test]
    fn test_message_id_prefix() {
        let ev = sample_event("Alert", "iDRAC.2.8.PDR0");
        let prefix = ev.message_id.split('.').next().unwrap();
        assert_eq!(prefix, "iDRAC");
    }
}
