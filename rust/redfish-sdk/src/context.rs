// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use std::sync::{Arc, Mutex};
use std::collections::HashMap;
use crate::errors::RedfishError;
use crate::transport::{HttpClient, AuthState, AuthManager, EndpointCapabilities, ConnectionConfig};
use crate::protocol::response::RedfishResponse;
use crate::discovery::Discovery;
use crate::services::event_service::EventServiceHandle;
use crate::services::log_service::LogServiceHandle;
use crate::services::ras_service::RasServiceHandle;
use crate::services::telemetry_service::TelemetryServiceHandle;
use crate::services::update_service::UpdateServiceHandle;

/// The opaque connection handle returned by `connect()`.
/// Move-only (`!Clone`), RAII — session is closed on drop.
pub struct ClientContext {
    pub(crate) http:          Box<dyn HttpClient>,
    pub(crate) auth_state:    AuthState,
    pub(crate) capabilities:  EndpointCapabilities,
    pub(crate) discovery_map: Arc<Mutex<HashMap<String, String>>>,
    pub(crate) config:        ConnectionConfig,
    pub(crate) base_path:     String,
    /// Owned runtime — used by blocking wrappers and logout in Drop.
    /// Wrapped in Option so Drop can take it and call forget() if we're
    /// inside an async context (dropping a Runtime inside async panics).
    pub(crate) runtime:       Option<Arc<tokio::runtime::Runtime>>,
}

// Not Clone — one connection per context.
impl std::fmt::Debug for ClientContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "ClientContext {{ base_url: {}, mode: {:?} }}", self.http.base_url(), self.auth_state.mode)
    }
}

impl Drop for ClientContext {
    fn drop(&mut self) {
        // Best-effort session logout.
        // Dropping a tokio Runtime from inside an async context panics.
        // Take the runtime Arc out first; if we're inside async, forget it
        // so it's never dropped here (the OS reclaims on process exit).
        let rt = match self.runtime.take() {
            Some(rt) => rt,
            None     => return, // no owned runtime — nothing to do
        };

        if tokio::runtime::Handle::try_current().is_ok() {
            // Inside async — forget the runtime instead of dropping it
            std::mem::forget(rt);
            return;
        }

        // Outside async — safe to block for logout
        let http  = self.http.as_ref();
        let state = &self.auth_state;
        let _ = rt.block_on(AuthManager::logout(http, state));
        // rt drops here (outside async) — safe
    }
}

impl ClientContext {
    // ── Internal constructor ─────────────────────────────────────────────────

    pub(crate) fn new(
        http:      Box<dyn HttpClient>,
        state:     AuthState,
        caps:      EndpointCapabilities,
        config:    ConnectionConfig,
        base_path: String,
        runtime:   Arc<tokio::runtime::Runtime>,
    ) -> Self {
        Self {
            http,
            auth_state:    state,
            capabilities:  caps,
            discovery_map: Arc::new(Mutex::new(HashMap::new())),
            config,
            base_path,
            runtime:       Some(runtime),
        }
    }

    // ── State ────────────────────────────────────────────────────────────────

    pub fn is_connected(&self) -> bool { true }

    pub fn base_url(&self) -> &str { self.http.base_url() }

    /// Return the negotiated endpoint capabilities.
    pub fn capabilities(&self) -> &crate::transport::types::EndpointCapabilities {
        &self.capabilities
    }

    // ── Service handles ──────────────────────────────────────────────────────

    pub fn event_service(&self)     -> EventServiceHandle<'_> {
        EventServiceHandle::new(self)
    }
    pub fn log_service(&self)       -> LogServiceHandle<'_> {
        LogServiceHandle::new(self)
    }
    pub fn telemetry_service(&self) -> TelemetryServiceHandle<'_> {
        TelemetryServiceHandle::new(self)
    }
    pub fn update_service(&self)    -> UpdateServiceHandle<'_> {
        UpdateServiceHandle::new(self)
    }
    pub fn ras_service(&self)        -> RasServiceHandle<'_> {
        RasServiceHandle::new(self)
    }
    pub fn discovery(&self) -> Discovery<'_> {
        Discovery {
            http:      self.http.as_ref(),
            state:     &self.auth_state,
            base_path: self.base_path.clone(),
            disc_map:  &self.discovery_map,
        }
    }

    // ── Direct / raw access ──────────────────────────────────────────────────

    pub async fn get(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.request("GET", uri, None).await
    }
    pub async fn post(&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        self.request("POST", uri, Some(body)).await
    }
    pub async fn patch(&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        self.request("PATCH", uri, Some(body)).await
    }
    pub async fn del(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.request("DELETE", uri, None).await
    }
    pub async fn put(&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        self.request("PUT", uri, Some(body)).await
    }
    pub fn put_blocking(&self, uri: &str, b: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        self.runtime.as_ref().expect("no runtime").block_on(self.put(uri, b))
    }

    pub fn get_blocking  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError> { self.runtime.as_ref().expect("no runtime").block_on(self.get(uri)) }
    pub fn post_blocking (&self, uri: &str, b: serde_json::Value) -> Result<RedfishResponse, RedfishError> { self.runtime.as_ref().expect("no runtime").block_on(self.post(uri, b)) }
    pub fn patch_blocking(&self, uri: &str, b: serde_json::Value) -> Result<RedfishResponse, RedfishError> { self.runtime.as_ref().expect("no runtime").block_on(self.patch(uri, b)) }
    pub fn del_blocking  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError> { self.runtime.as_ref().expect("no runtime").block_on(self.del(uri)) }

    // ── Auth refresh ─────────────────────────────────────────────────────────

    pub async fn refresh_auth(&mut self) -> Result<(), RedfishError> {
        let mgr = AuthManager::new(
            self.http.as_ref(),
            self.auth_state.credentials.clone(),
            self.auth_state.mode.clone(),
            &self.base_path,
        );
        self.auth_state = mgr.authenticate().await?;
        Ok(())
    }

    pub fn refresh_auth_blocking(&mut self) -> Result<(), RedfishError> {
        let rt = Arc::clone(self.runtime.as_ref().expect("no runtime"));
        rt.block_on(self.refresh_auth())
    }

    // ── Internal helper ──────────────────────────────────────────────────────

    pub(crate) async fn request(
        &self,
        method: &str,
        uri:    &str,
        body:   Option<serde_json::Value>,
    ) -> Result<RedfishResponse, RedfishError> {
        let mut headers = HashMap::new();
        AuthManager::attach_auth(&self.auth_state, &mut headers);
        let raw = self.http.request(method, uri, headers, body).await?;

        // Transparent 401 re-auth: not implemented in v0.1 — callers use refresh_auth().
        Ok(RedfishResponse::from_raw(raw))
    }

    /// Return a resolved URI for a well-known service name.
    pub(crate) fn resolve_service_uri(&self, name: &str, fallback: &str) -> String {
        self.discovery_map.lock().ok()
            .and_then(|m| m.get(name).cloned())
            .unwrap_or_else(|| format!("{}{}", self.base_path, fallback))
    }
}
