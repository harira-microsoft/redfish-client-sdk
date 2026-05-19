// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

//! RAS API service handle — endpoint discovery, CPER event subscription,
//! large-CPER retrieval via AdditionalDataUri, and CPAD submission.
//!
//! Terminology:
//! - **CPER**  — Common Platform Error Record (UEFI 2.9A)
//! - **CPAD**  — Common Platform Action Descriptor (OCP RAS API v1.0)
//! - **CreatorID**   — GUID identifying the vendor analyzer for a CPER stream.
//! - **PartitionID** — BMC-assigned routing ID used to direct CPADs to the
//!                     correct silicon endpoint.

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde_json::json;

use crate::context::ClientContext;
use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;

// ---------------------------------------------------------------------------
// CPER severity / queue types
// ---------------------------------------------------------------------------

/// Maps to the five RAS API CPER queues defined in the OCP RAS API v1.0 spec.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CperSeverity {
    /// Informational / Platform Action Events (not error events)
    PlatformEvent,
    /// Deferred errors including poison generation
    Informational,
    /// Hardware-corrected errors
    Corrected,
    /// OS-survivable errors (poison consumption, PCIe device failure)
    Recoverable,
    /// OS-crashing errors / hardware crashdumps
    Fatal,
}

impl CperSeverity {
    /// Infer severity from a Redfish MessageId string (case-insensitive).
    pub fn from_message_id(message_id: &str) -> Option<Self> {
        let lower = message_id.to_lowercase();
        if lower.contains("platformevent") { return Some(Self::PlatformEvent); }
        if lower.contains("informational")  { return Some(Self::Informational); }
        if lower.contains("corrected")      { return Some(Self::Corrected); }
        if lower.contains("recoverable")    { return Some(Self::Recoverable); }
        if lower.contains("fatal")          { return Some(Self::Fatal); }
        None
    }
}

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

/// A silicon RAS API endpoint discovered by the BMC and exposed via Redfish.
#[derive(Debug, Clone)]
pub struct RasEndpoint {
    pub endpoint_id:      String,
    pub creator_id:       String,           // GUID — identifies the vendor analyzer
    pub fru_id:           String,           // GUID — unique FRU instance identifier
    pub partition_id:     String,           // BMC-assigned routing ID for CPADs
    pub supported_queues: Vec<String>,
    pub uri:              String,
    pub raw:              serde_json::Value,
}

/// A CPER-carrying Redfish event delivered by the BMC.
///
/// For small CPERs `cper_data` is populated with the decoded bytes.
/// For large CPERs `additional_data_uri` is set; call
/// [`RasServiceHandle::fetch_cper_data`] to retrieve the binary payload.
#[derive(Debug, Clone)]
pub struct CperEvent {
    pub event_id:            String,
    pub message_id:          String,
    pub severity:            Option<CperSeverity>,
    pub timestamp:           String,
    pub origin_of_condition: Option<String>,
    pub cper_data:           Option<Vec<u8>>,  // inline CPER bytes
    pub additional_data_uri: Option<String>,   // URI for large-CPER retrieval
    pub raw:                 serde_json::Value,
}

impl CperEvent {
    /// Parse a single EventRecord object from a Redfish EventMessage payload.
    pub fn from_event_record(record: &serde_json::Value) -> Self {
        let message_id = record["MessageId"].as_str().unwrap_or("").to_string();
        let severity   = CperSeverity::from_message_id(&message_id);

        // Attempt to decode an inline CPER from known field locations
        let cper_data = ["AdditionalData"]
            .iter()
            .find_map(|&key| {
                record.get(key)?.as_str().and_then(|s| BASE64.decode(s).ok())
            })
            .or_else(|| {
                record.pointer("/Oem/CperData")
                    .and_then(|v| v.as_str())
                    .and_then(|s| BASE64.decode(s).ok())
            });

        CperEvent {
            event_id:            record["EventId"].as_str().unwrap_or("").to_string(),
            message_id,
            severity,
            timestamp:           record["EventTimestamp"].as_str().unwrap_or("").to_string(),
            origin_of_condition: record.pointer("/OriginOfCondition/@odata.id")
                                       .and_then(|v| v.as_str())
                                       .map(|s| s.to_string()),
            cper_data,
            additional_data_uri: record["AdditionalDataURI"].as_str().map(|s| s.to_string()),
            raw:                 record.clone(),
        }
    }
}

/// A Common Platform Action Descriptor (CPAD) to submit to the BMC.
///
/// The BMC uses `partition_id` to route the action to the correct silicon
/// endpoint.  `payload` is the raw binary CPAD blob transmitted base64-encoded
/// in the JSON body.
#[derive(Debug, Clone)]
pub struct CpadRecord {
    pub platform_id:  String,    // identifies this BMC in the fleet
    pub partition_id: String,    // identifies the target silicon endpoint
    pub creator_id:   String,    // identifies the issuing analyzer
    pub payload:      Vec<u8>,   // binary CPAD blob
    pub fru_id:       String,
    pub fru_text:     String,    // physical location label (e.g. silkscreen)
}

// ---------------------------------------------------------------------------
// Service handle
// ---------------------------------------------------------------------------

/// Redfish client handle for the RAS API service.
pub struct RasServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> RasServiceHandle<'ctx> {
    pub(crate) fn new(ctx: &'ctx ClientContext) -> Self { Self { ctx } }

    fn service_uri(&self) -> String {
        self.ctx.resolve_service_uri("RasService", "/RasService")
    }

    fn event_subscriptions_uri(&self) -> String {
        let svc = self.ctx.resolve_service_uri("EventService", "/EventService");
        format!("{}/Subscriptions", svc)
    }

    // ── Async ────────────────────────────────────────────────────────────────

    /// Discover all RAS API endpoints exposed by the BMC.
    pub async fn discover_endpoints(&self) -> Result<Vec<RasEndpoint>, RedfishError> {
        let resp = self.ctx.get(&self.service_uri()).await?;
        if !resp.success { return Ok(vec![]); }

        let empty = serde_json::json!([]);
        let members = resp.body
            .as_ref()
            .and_then(|b| b.get("Members"))
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();

        let mut endpoints = Vec::new();
        for member in &members {
            let uri = match member.get("@odata.id").and_then(|v| v.as_str()) {
                Some(u) => u,
                None    => continue,
            };
            let detail = self.ctx.get(uri).await?;
            if !detail.success { continue; }
            let null = serde_json::Value::Null;
            let d = detail.body.as_ref().unwrap_or(&null);
            endpoints.push(RasEndpoint {
                endpoint_id:      d["Id"].as_str().unwrap_or("").to_string(),
                creator_id:       d["CreatorId"].as_str().unwrap_or("").to_string(),
                fru_id:           d["FruId"].as_str().unwrap_or("").to_string(),
                partition_id:     d["PartitionId"].as_str().unwrap_or("").to_string(),
                supported_queues: d["SupportedQueues"].as_array()
                    .map(|a| a.iter()
                              .filter_map(|v| v.as_str().map(|s| s.to_string()))
                              .collect())
                    .unwrap_or_default(),
                uri: uri.to_string(),
                raw: d.clone(),
            });
        }
        drop(empty);
        Ok(endpoints)
    }

    /// Subscribe to CPER-carrying Redfish events from this BMC.
    ///
    /// Leave `registry_prefixes` and `message_ids` empty to receive all events
    /// and filter client-side with [`parse_cper_events`].
    pub async fn subscribe_cper_events(
        &self,
        destination:       &str,
        registry_prefixes: Vec<String>,
        message_ids:       Vec<String>,
        context:           &str,
        event_format_type: &str,
    ) -> Result<RedfishResponse, RedfishError> {
        let subs_uri = self.event_subscriptions_uri();
        let mut body = json!({
            "Destination":      destination,
            "Protocol":         "Redfish",
            "SubscriptionType": "RedfishEvent",
            "Context":          context,
            "EventFormatType":  event_format_type,
        });
        if !registry_prefixes.is_empty() {
            body["RegistryPrefixes"] = json!(registry_prefixes);
        }
        if !message_ids.is_empty() {
            body["MessageIds"] = json!(message_ids);
        }
        self.ctx.post(&subs_uri, body).await
    }

    /// Fetch a CPER payload from the BMC via the `AdditionalDataUri` in an event.
    pub async fn fetch_cper_data(&self, additional_data_uri: &str) -> Result<Vec<u8>, RedfishError> {
        let resp = self.ctx.get(additional_data_uri).await?;
        if !resp.success {
            return Err(RedfishError::HttpError {
                status_code: resp.status_code,
                message: format!("Failed to fetch CPER data from {additional_data_uri}"),
            });
        }

        // Try known base64-encoded fields in priority order
        if let Some(body) = &resp.body {
            for key in &["CperData", "Data", "AdditionalData"] {
                if let Some(s) = body.get(key).and_then(|v| v.as_str()) {
                    if let Ok(bytes) = BASE64.decode(s) {
                        return Ok(bytes);
                    }
                }
            }
            // Fallback: return JSON body serialised as bytes
            return Ok(serde_json::to_vec(body).unwrap_or_default());
        }

        Ok(vec![])
    }

    /// Submit a CPAD to the BMC via HTTP PUT.
    ///
    /// Action completion is confirmed asynchronously via a Platform Action Event
    /// CPER on the Event queue after the BMC routes the CPAD to the silicon endpoint.
    pub async fn submit_cpad(
        &self,
        cpad_uri: &str,
        cpad:     &CpadRecord,
    ) -> Result<RedfishResponse, RedfishError> {
        let body = json!({
            "PlatformId":  cpad.platform_id,
            "PartitionId": cpad.partition_id,
            "CreatorId":   cpad.creator_id,
            "FruId":       cpad.fru_id,
            "FruText":     cpad.fru_text,
            "Payload":     BASE64.encode(&cpad.payload),
        });
        self.ctx.put(cpad_uri, body).await
    }

    /// Parse `CperEvent` objects from a Redfish EventMessage payload.
    ///
    /// Non-RAS event records in the same payload are silently ignored.
    pub fn parse_cper_events(event_payload: &serde_json::Value) -> Vec<CperEvent> {
        let events = event_payload.get("Events")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        events.iter()
              .map(CperEvent::from_event_record)
              .filter(|ev| {
                  ev.severity.is_some()
                  || ev.message_id.to_lowercase().contains("cper")
                  || ev.message_id.to_lowercase().contains("ras")
              })
              .collect()
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn discover_endpoints_blocking(&self) -> Result<Vec<RasEndpoint>, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.discover_endpoints())
    }

    pub fn subscribe_cper_events_blocking(
        &self,
        destination:       &str,
        registry_prefixes: Vec<String>,
        message_ids:       Vec<String>,
        context:           &str,
        event_format_type: &str,
    ) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(
            self.subscribe_cper_events(destination, registry_prefixes, message_ids, context, event_format_type)
        )
    }

    pub fn fetch_cper_data_blocking(&self, uri: &str) -> Result<Vec<u8>, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.fetch_cper_data(uri))
    }

    pub fn submit_cpad_blocking(&self, cpad_uri: &str, cpad: &CpadRecord) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.submit_cpad(cpad_uri, cpad))
    }
}
