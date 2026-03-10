// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

//! Redfish Client SDK — idiomatic Rust
//!
//! # Quick start
//!
//! ```no_run
//! use redfish_sdk::{connect, Credentials, AuthMode, ConnectionConfig};
//! use redfish_sdk::services::log_service::LogQuery;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), redfish_sdk::RedfishError> {
//!     let creds = Credentials::new("admin", "password");
//!     let ctx = connect("BMC_HOST", 443, creds, AuthMode::Session,
//!                       ConnectionConfig::default()).await?;
//!
//!     let log = ctx.log_service();
//!     let entries = log.list_entries("/redfish/v1/Systems/system/LogServices/SEL",
//!                                   LogQuery::default()).await?;
//!     if let Some(body) = &entries.body {
//!         println!("Got log entries: {:?}", body);
//!     }
//!     Ok(())
//! }
//! ```

// ── Internal modules ─────────────────────────────────────────────────────────
mod errors;
mod transport;
mod context;
mod client;

// ── Public modules ───────────────────────────────────────────────────────────
pub mod protocol;
pub mod discovery;
pub mod services;
pub mod events;

// ── Top-level re-exports ─────────────────────────────────────────────────────

/// Connect to a Redfish BMC asynchronously and return a [`ClientContext`].
pub use client::{connect, connect_blocking};

/// The main connection context.  All service handles are obtained from here.
pub use context::ClientContext;

/// Unified error type for the SDK.
pub use errors::RedfishError;

// Transport primitives callers need to construct a connection.
pub use transport::types::{AuthMode, ConnectionConfig, Credentials, EndpointCapabilities};

// Protocol types.
pub use protocol::response::{RedfishMessage, RedfishResponse};
pub use protocol::task::RedfishTask;

// Discovery.
pub use discovery::DiscoveryResult;

// Service handle types.
pub use services::event_service::EventServiceHandle;
pub use services::log_service::{LogQuery, SelEntry, LogServiceHandle};
pub use services::telemetry_service::TelemetryServiceHandle;
pub use services::update_service::UpdateServiceHandle;

// Event listener.
pub use events::{RedfishEvent, RedfishEventListener};
