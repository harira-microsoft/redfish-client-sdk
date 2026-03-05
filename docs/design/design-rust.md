# Redfish Client SDK — Rust Design

**Document ID:** RSDK-DESIGN-003  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Architecture Ref:** RSDK-ARCH-001, RSDK-ARCH-004  
**API Reference:** RSDK-DESIGN-001 (Python), RSDK-DESIGN-002 (C++)  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Design Principles](#2-design-principles)
3. [Module Structure](#3-module-structure)
4. [SDK Entry Point — connect()](#4-sdk-entry-point--connect)
5. [ClientContext](#5-clientcontext)
6. [ConnectionConfig](#6-connectionconfig)
7. [Discovery](#7-discovery)
8. [RedfishResponse](#8-redfishresponse)
9. [RedfishTask and TaskManager](#9-redfishask-and-taskmanager)
10. [MessageRegistry](#10-messageregistry)
11. [EventServiceHandle](#11-eventservicehandle)
12. [LogServiceHandle](#12-logservicehandle)
13. [TelemetryServiceHandle](#13-telemetryservicehandle)
14. [UpdateServiceHandle](#14-updateservicehandle)
15. [RedfishEventListener](#15-redfisheventlistener)
16. [Transport Layer — HttpClient](#16-transport-layer--httpclient)
17. [Transport Layer — AuthManager](#17-transport-layer--authmanager)
18. [Transport Layer — TLS](#18-transport-layer--tls)
19. [Internal Data Contracts](#19-internal-data-contracts)
20. [Error Design](#20-error-design)
21. [Async and Sync Model](#21-async-and-sync-model)
22. [Ownership and Lifetime Contracts](#22-ownership-and-lifetime-contracts)
23. [Change History](#23-change-history)

---

## 1. Purpose

This document defines the detailed design of the Rust SDK (Phase 3). It mirrors
the Python design (RSDK-DESIGN-001) and C++ design (RSDK-DESIGN-002) in
structure and API surface, expressed idiomatically in Rust.

A developer assigned to any component can start from this document without
making design decisions.

**This is idiomatic Rust — not a port of the C++ SDK.** Where Rust has a
better native expression (ownership, `Result`, lifetimes, traits), it is used.

---

## 2. Design Principles

| Principle | Rust Expression |
|---|---|
| One entry point | `redfish_sdk::connect()` free async fn — callers never construct `ClientContext` directly |
| Opaque handle | All `ClientContext` fields are private — compiler enforces this |
| Move-only context | `ClientContext` does not implement `Clone` — one owner, enforced at compile time |
| Async-first | All logic in `async fn`; sync variants use `_blocking` suffix via `tokio::runtime` |
| RAII | `Drop` impl on `ClientContext` closes session; `Drop` on `RedfishEventListener` stops server |
| Uniform response | Every public method returns `Result<RedfishResponse, RedfishError>` |
| Handles borrow context | Service handles carry a lifetime `'ctx` — they cannot outlive the context |
| Errors are values | `RedfishError` is an enum — callers `match` on variants, no `try/catch` |

---

## 3. Module Structure

```
redfish-sdk/src/
├── lib.rs                      ← pub use: connect, connect_blocking, RedfishEventListener,
│                                          RedfishError, ConnectionConfig, Credentials, AuthMode
├── client.rs                   ← connect() and connect_blocking()
├── context.rs                  ← ClientContext struct and impl
│
├── discovery/
│   ├── mod.rs
│   └── discovery.rs            ← Discovery<'ctx>, DiscoveryResult
│
├── services/
│   ├── mod.rs
│   ├── event_service.rs        ← EventServiceHandle<'ctx>
│   ├── log_service.rs          ← LogServiceHandle<'ctx>
│   ├── telemetry_service.rs    ← TelemetryServiceHandle<'ctx>
│   └── update_service.rs       ← UpdateServiceHandle<'ctx>
│
├── events/
│   ├── mod.rs
│   └── listener.rs             ← RedfishEventListener
│
├── protocol/
│   ├── mod.rs
│   ├── response.rs             ← RedfishResponse, RedfishMessage
│   ├── task.rs                 ← RedfishTask (pub), TaskManager (pub(crate))
│   └── registry.rs             ← MessageRegistry (pub(crate))
│
└── transport/
    ├── mod.rs                  ← pub(crate) only — not accessible outside the crate
    ├── http_client.rs          ← HttpClient, RawHttpResponse
    ├── auth.rs                 ← AuthManager, AuthState
    └── tls.rs                  ← build_tls_config()
```

**Visibility rules:**
- `transport/` is `pub(crate)` — callers cannot reach it
- `protocol/` types are `pub` (response, task) or `pub(crate)` (registry, task manager)
- `services/`, `discovery/`, `events/` are `pub`
- `context.rs` fields are all private — only methods are public

---

## 4. SDK Entry Point — connect()

### Module: `client.rs`
### Re-exported from: `lib.rs`

### Signatures

```rust
// Async (primary)
pub async fn connect(
    host:        &str,
    port:        u16,
    credentials: Credentials,
    auth_mode:   AuthMode,
    config:      ConnectionConfig,
) -> Result<ClientContext, RedfishError>

// Sync wrapper
pub fn connect_blocking(
    host:        &str,
    port:        u16,
    credentials: Credentials,
    auth_mode:   AuthMode,
    config:      ConnectionConfig,
) -> Result<ClientContext, RedfishError>
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `host` | `&str` | Hostname or IP address |
| `port` | `u16` | Port (443 for BMC, 8000 for simulator) |
| `credentials` | `Credentials` | Username + password (see §19) |
| `auth_mode` | `AuthMode` | `AuthMode::Session` or `AuthMode::Stateless` |
| `config` | `ConnectionConfig` | Pass `ConnectionConfig::default()` for all defaults |

### AuthMode

```rust
pub enum AuthMode {
    Session,
    Stateless,
}
```

### Failure (returns Err variant)

| Failure | `RedfishError` variant |
|---|---|
| Host unreachable | `RedfishError::ConnectionFailed` |
| TLS certificate rejected | `RedfishError::TlsError` |
| 401 / 403 | `RedfishError::AuthFailed` |
| Endpoint not Redfish-compliant | `RedfishError::ProtocolError` |

---

## 5. ClientContext

### Module: `context.rs`
### Re-exported from: `lib.rs`

### Struct Definition

```rust
pub struct ClientContext {
    http_client:   transport::HttpClient,
    auth_state:    transport::AuthState,
    capabilities:  EndpointCapabilities,
    schema_cache:  HashMap<String, serde_json::Value>,
    discovery_map: HashMap<String, String>,
    config:        ConnectionConfig,
    runtime:       Arc<tokio::runtime::Runtime>,    // for sync (_blocking) variants
}
```

All fields are private. The struct is constructed only inside `connect()`.

### Trait Implementations

| Trait | Implemented? | Reason |
|---|---|---|
| `Clone` | ❌ No | One connection per context — enforced at compile time |
| `Send` | ✅ Yes | Context can be moved across thread boundaries |
| `Sync` | ❌ No | Not designed for shared concurrent access |
| `Drop` | ✅ Yes | Closes session / releases transport on drop |
| `Debug` | ✅ Yes | Prints connection info only — never secrets |

### Public Interface

```rust
impl ClientContext {
    // State
    pub fn is_connected(&self) -> bool;
    pub fn base_url(&self) -> &str;

    // Service handles — returned with borrowed lifetime
    pub fn event_service(&self)     -> EventServiceHandle<'_>;
    pub fn log_service(&self)       -> LogServiceHandle<'_>;
    pub fn telemetry_service(&self) -> TelemetryServiceHandle<'_>;
    pub fn update_service(&self)    -> UpdateServiceHandle<'_>;
    pub fn discovery(&self)         -> Discovery<'_>;

    // Direct / raw access — async
    pub async fn get  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError>;
    pub async fn post (&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError>;
    pub async fn patch(&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError>;
    pub async fn del  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError>;

    // Sync variants
    pub fn get_blocking  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError>;
    pub fn post_blocking (&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError>;
    pub fn patch_blocking(&self, uri: &str, body: serde_json::Value) -> Result<RedfishResponse, RedfishError>;
    pub fn del_blocking  (&self, uri: &str)                       -> Result<RedfishResponse, RedfishError>;
}
```

### Drop Implementation

```rust
impl Drop for ClientContext {
    fn drop(&mut self) {
        // Attempt session logout (best-effort; errors ignored on drop)
        // Releases HttpClient and all owned state
    }
}
```

### Service Handle Lifetime

Service handles borrow `&self` and carry `'_`. The compiler prevents the
handle from outliving the context.

```rust
// This compiles:
let ctx = connect(...).await?;
let svc = ctx.event_service();  // borrows ctx
svc.get_service_info().await?;

// This does NOT compile:
let svc = {
    let ctx = connect(...).await?;
    ctx.event_service()          // ERROR: svc would outlive ctx
};
```

---

## 6. ConnectionConfig

### Module: `context.rs` (or `lib.rs`)

```rust
#[derive(Debug, Clone)]
pub struct ConnectionConfig {
    pub verify_tls:              bool,           // default: true
    pub tls_ca_cert:             Option<String>, // default: None (system CA store)
    pub connect_timeout_secs:    f32,            // default: 10.0
    pub request_timeout_secs:    f32,            // default: 30.0
    pub task_poll_interval_secs: f32,            // default: 5.0
    pub task_timeout_secs:       f32,            // default: 300.0
    pub base_path_override:      Option<String>, // default: None → /redfish/v1
}

impl Default for ConnectionConfig {
    fn default() -> Self { /* all defaults as above */ }
}
```

Callers pass `ConnectionConfig::default()` to accept all defaults, or
use struct update syntax: `ConnectionConfig { verify_tls: false, ..Default::default() }`.

---

## 7. Discovery

### Module: `discovery/discovery.rs`
### Accessed via: `ctx.discovery()`

### Struct

```rust
pub struct Discovery<'ctx> {
    ctx: &'ctx ClientContext,
}
```

### Public Interface

```rust
impl<'ctx> Discovery<'ctx> {
    // Async
    pub async fn full   (&self)                    -> Result<DiscoveryResult, RedfishError>;
    pub async fn partial(&self, service: &str)     -> Result<DiscoveryResult, RedfishError>;
    pub async fn root   (&self)                    -> Result<DiscoveryResult, RedfishError>;

    // Sync
    pub fn full_blocking   (&self)                -> Result<DiscoveryResult, RedfishError>;
    pub fn partial_blocking(&self, service: &str) -> Result<DiscoveryResult, RedfishError>;
    pub fn root_blocking   (&self)                -> Result<DiscoveryResult, RedfishError>;
}
```

### Discovery Modes

| Mode | Method | Behaviour |
|---|---|---|
| **Root** | `root()` | GET `/redfish/v1` only — enumerate top-level links, no traversal |
| **Partial** | `partial(name)` | GET ServiceRoot, then GET the named service only |
| **Full** | `full()` | GET ServiceRoot, then GET all top-level service links one level deep |

### DiscoveryResult

```rust
#[derive(Debug)]
pub struct DiscoveryResult {
    pub services:     HashMap<String, String>,  // service name → URI
    pub capabilities: Vec<String>,              // service names found
    pub raw:          serde_json::Value,        // raw ServiceRoot JSON
}

impl DiscoveryResult {
    pub fn has_service(&self, name: &str) -> bool;
    pub fn service_uri(&self, name: &str) -> Option<&str>;
}
```

### Side Effect

After any discovery call, `ClientContext::discovery_map` is updated via
interior mutability (`RefCell` or `Mutex` depending on `Send` requirement).
Service handles use this map to resolve their target URI.

---

## 8. RedfishResponse

### Module: `protocol/response.rs`
### Re-exported from: `lib.rs`

```rust
#[derive(Debug, Clone)]
pub struct RedfishMessage {
    pub message_id:   String,
    pub message:      String,
    pub severity:     String,
    pub resolution:   Option<String>,
    pub message_args: Vec<String>,
}

#[derive(Debug)]
pub struct RedfishResponse {
    pub status_code:   u16,
    pub success:       bool,                        // true if 2xx
    pub headers:       HashMap<String, String>,
    pub body:          Option<serde_json::Value>,   // None if no body
    pub extended_info: Vec<RedfishMessage>,
    pub task:          Option<RedfishTask>,         // populated on 202
    pub raw:           String,
}
```

`RedfishResponse` is an owned value type. All fields are `pub` — callers
read them directly. No getters needed in Rust for plain struct fields.

---

## 9. RedfishTask and TaskManager

### Module: `protocol/task.rs`

### RedfishTask (Public)

```rust
#[derive(Debug)]
pub struct RedfishTask {
    pub task_uri:         String,
    pub task_id:          String,
    pub state:            TaskState,
    pub percent_complete: Option<u8>,
    pub messages:         Vec<RedfishMessage>,

    // private: holds a reference back into the context for polling
    ctx: /* non-pub reference to transport */,
}

impl RedfishTask {
    // Async — awaits terminal state
    pub async fn wait(
        &mut self,
        poll_interval_secs: Option<f32>,
        timeout_secs:       Option<f32>,
    ) -> Result<RedfishResponse, RedfishError>;

    // Sync
    pub fn wait_blocking(
        &mut self,
        poll_interval_secs: Option<f32>,
        timeout_secs:       Option<f32>,
    ) -> Result<RedfishResponse, RedfishError>;

    // Async — callback on each state change
    pub async fn monitor<F, Fut>(
        &mut self,
        on_state_change: F,
        timeout_secs:    Option<f32>,
    ) -> Result<(), RedfishError>
    where
        F:   Fn(TaskState, &RedfishTask) -> Fut,
        Fut: std::future::Future<Output = ()>;

    // Cancel the task
    pub async fn cancel(&self)          -> Result<RedfishResponse, RedfishError>;
    pub fn cancel_blocking(&self)       -> Result<RedfishResponse, RedfishError>;
}
```

### TaskState Enum

```rust
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub enum TaskState {
    New, Starting, Running, Suspended, Interrupted,
    Pending, Stopping, Completed, Killed, Exception,
    Service, Cancelling, Cancelled,
}
```

Terminal states (polling stops): `Completed`, `Killed`, `Exception`, `Cancelled`.

### TaskManager (Internal — `pub(crate)`)

Not part of the public API. Used by `RedfishTask::wait()` and `wait_blocking()`.

Behaviour:
1. Poll task URI at `poll_interval_secs` intervals using `tokio::time::interval`
2. Parse `TaskState` and `percent_complete` from each response
3. Update `RedfishTask` fields on each poll
4. Invoke `on_state_change` closure if registered
5. Stop at terminal state or timeout
6. On timeout → `Err(RedfishError::Timeout)`
7. On terminal failure state → `Err(RedfishError::TaskFailed)`

---

## 10. MessageRegistry

### Module: `protocol/registry.rs`
### Visibility: `pub(crate)`

Used internally by service handles and `RedfishEventListener` for
`MessageId` resolution.

```rust
pub(crate) struct MessageRegistry<'ctx> {
    ctx:   &'ctx ClientContext,
    cache: HashMap<String, serde_json::Value>,
}

impl<'ctx> MessageRegistry<'ctx> {
    pub(crate) async fn resolve(&mut self, message_id: &str)
        -> Option<RedfishMessage>;

    pub(crate) async fn fetch(&mut self, registry_prefix: &str)
        -> Result<bool, RedfishError>;
}
```

### MessageId Format

```
RegistryPrefix.MajorVersion.MinorVersion.MessageKey
Example: Base.1.8.Success
```

### Resolution Flow

Parse prefix → check `cache` → on miss: GET `/redfish/v1/Registries/{prefix}/{prefix}.json`
→ insert into `cache` → look up key → return `Some(RedfishMessage)`. Returns
`None` if the registry or key is not found. Cache lives for the lifetime of
the `MessageRegistry` instance.

---

## 11. EventServiceHandle

### Module: `services/event_service.rs`
### Accessed via: `ctx.event_service()`

```rust
pub struct EventServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}
```

### URI Resolution

Priority order:
1. `ctx.discovery_map.get("EventService")`
2. `{base_url}/redfish/v1/EventService`

### Public Interface

```rust
impl<'ctx> EventServiceHandle<'ctx> {
    pub async fn get_service_info(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn subscribe(
        &self,
        destination:       &str,
        event_types:       Vec<String>,
        registry_prefixes: Vec<String>,
        message_ids:       Vec<String>,
        context:           Option<&str>,
        protocol:          &str,            // default: "Redfish"
        subscription_type: &str,            // default: "RedfishEvent"
    ) -> Result<RedfishResponse, RedfishError>;

    pub async fn list_subscriptions(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_subscription(&self, subscription_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn delete_subscription(&self, subscription_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    // SSE streaming — yields RedfishEvent items; runs until the stream ends or is dropped
    pub async fn subscribe_sse(
        &self,
        filters: Option<serde_json::Value>,
    ) -> Result<impl futures::Stream<Item = Result<RedfishEvent, RedfishError>>, RedfishError>;

    pub async fn submit_test_event(&self, event_data: serde_json::Value)
        -> Result<RedfishResponse, RedfishError>;

    // Sync variants (_blocking suffix)
    pub fn get_service_info_blocking(&self)    -> Result<RedfishResponse, RedfishError>;
    pub fn subscribe_blocking(&self, /* same params */) -> Result<RedfishResponse, RedfishError>;
    pub fn list_subscriptions_blocking(&self)  -> Result<RedfishResponse, RedfishError>;
    pub fn get_subscription_blocking(&self, subscription_uri: &str) -> Result<RedfishResponse, RedfishError>;
    pub fn delete_subscription_blocking(&self, subscription_uri: &str) -> Result<RedfishResponse, RedfishError>;
}
```

### RedfishEvent

```rust
#[derive(Debug, Clone)]
pub struct RedfishEvent {
    pub event_id:             String,
    pub event_type:           String,
    pub event_timestamp:      String,
    pub message_id:           String,
    pub message:              String,
    pub severity:             String,
    pub origin_of_condition:  Option<String>,
    pub raw:                  serde_json::Value,
}
```

### SSE vs Push

- `subscribe_sse` returns a `Stream` of events over a persistent HTTP connection.
- Push delivery uses `RedfishEventListener` (production BMC environments).

---

## 12. LogServiceHandle

### Module: `services/log_service.rs`
### Accessed via: `ctx.log_service()`

```rust
pub struct LogServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> LogServiceHandle<'ctx> {
    pub async fn list_services(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_entries(
        &self,
        log_service_uri: &str,
        filter:          Option<LogFilter>,
    ) -> Result<RedfishResponse, RedfishError>;

    pub async fn get_entry(&self, entry_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn clear_log(&self, log_service_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    // Sync variants
    pub fn list_services_blocking(&self)         -> Result<RedfishResponse, RedfishError>;
    pub fn get_entries_blocking(&self, log_service_uri: &str, filter: Option<LogFilter>)
        -> Result<RedfishResponse, RedfishError>;
    pub fn get_entry_blocking(&self, entry_uri: &str)      -> Result<RedfishResponse, RedfishError>;
    pub fn clear_log_blocking(&self, log_service_uri: &str) -> Result<RedfishResponse, RedfishError>;
}
```

### LogFilter

```rust
#[derive(Debug, Default)]
pub struct LogFilter {
    pub severity:    Option<String>,    // "OK" | "Warning" | "Critical"
    pub start_time:  Option<String>,    // ISO 8601
    pub end_time:    Option<String>,    // ISO 8601
    pub message_id:  Option<String>,    // filter by MessageId prefix
    pub max_entries: Option<usize>,
}
```

---

## 13. TelemetryServiceHandle

### Module: `services/telemetry_service.rs`
### Accessed via: `ctx.telemetry_service()`

```rust
pub struct TelemetryServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> TelemetryServiceHandle<'ctx> {
    pub async fn get_service_info(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn list_metric_report_definitions(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_metric_report_definition(&self, definition_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn list_metric_reports(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_metric_report(&self, report_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    // Streaming — yields MetricReport items; runs until stream ends or is dropped
    pub async fn stream_metric_reports(
        &self,
        definition_uri: Option<&str>,
    ) -> Result<impl futures::Stream<Item = Result<MetricReport, RedfishError>>, RedfishError>;

    // Sync variants
    pub fn get_service_info_blocking(&self)                  -> Result<RedfishResponse, RedfishError>;
    pub fn list_metric_report_definitions_blocking(&self)    -> Result<RedfishResponse, RedfishError>;
    pub fn get_metric_report_definition_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError>;
    pub fn list_metric_reports_blocking(&self)               -> Result<RedfishResponse, RedfishError>;
    pub fn get_metric_report_blocking(&self, report_uri: &str) -> Result<RedfishResponse, RedfishError>;
}
```

### MetricReport and MetricValue

```rust
#[derive(Debug, Clone, Deserialize)]
pub struct MetricValue {
    pub metric_id:       String,
    pub metric_value:    String,            // raw string; caller parses if numeric
    pub timestamp:       String,
    pub metric_property: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MetricReport {
    pub report_id:     String,
    pub report_uri:    String,
    pub timestamp:     String,
    pub metric_values: Vec<MetricValue>,
    pub raw:           serde_json::Value,
}
```

---

## 14. UpdateServiceHandle

### Module: `services/update_service.rs`
### Accessed via: `ctx.update_service()`

```rust
pub struct UpdateServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> UpdateServiceHandle<'ctx> {
    pub async fn get_service_info(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn list_firmware_inventory(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_firmware_component(&self, component_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn list_software_inventory(&self)
        -> Result<RedfishResponse, RedfishError>;

    pub async fn get_software_component(&self, component_uri: &str)
        -> Result<RedfishResponse, RedfishError>;

    // Returns Ok(response); response.task is Some if BMC returned 202
    pub async fn simple_update(
        &self,
        image_uri:         &str,
        targets:           Vec<String>,
        transfer_protocol: Option<&str>,
        apply_time:        Option<&str>,
    ) -> Result<RedfishResponse, RedfishError>;

    // Sync variants
    pub fn get_service_info_blocking(&self)            -> Result<RedfishResponse, RedfishError>;
    pub fn list_firmware_inventory_blocking(&self)     -> Result<RedfishResponse, RedfishError>;
    pub fn get_firmware_component_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError>;
    pub fn list_software_inventory_blocking(&self)     -> Result<RedfishResponse, RedfishError>;
    pub fn get_software_component_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError>;
    pub fn simple_update_blocking(&self, /* same params */) -> Result<RedfishResponse, RedfishError>;
}
```

---

## 15. RedfishEventListener

### Module: `events/listener.rs`
### Re-exported from: `lib.rs`

### Struct

```rust
pub struct RedfishEventListener {
    port:        u16,
    host:        String,
    tls_cert:    Option<String>,
    tls_key:     Option<String>,
    callbacks:   Arc<Mutex<CallbackRegistry>>,
    join_handle: Option<tokio::task::JoinHandle<()>>,
}
```

### Public Interface

```rust
impl RedfishEventListener {
    pub fn new(port: u16) -> Self;

    pub fn with_host(self, host: &str) -> Self;        // builder pattern
    pub fn with_tls(self, cert: &str, key: &str) -> Self;

    // Wire to context for MessageRegistry decoding (optional)
    pub fn use_context(&mut self, ctx: &ClientContext);

    // Register callbacks — accept any async closure
    pub fn on_event<F, Fut>(&mut self, callback: F)
    where
        F:   Fn(RedfishEvent) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static;

    pub fn on_event_type<F, Fut>(&mut self, event_type: &str, callback: F)
    where
        F:   Fn(RedfishEvent) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static;

    pub fn on_registry<F, Fut>(&mut self, registry_prefix: &str, callback: F)
    where
        F:   Fn(RedfishEvent) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static;

    // Lifecycle
    pub async fn start(&mut self) -> Result<(), RedfishError>;
    pub async fn stop(&mut self);

    pub fn is_running(&self)  -> bool;
    pub fn listen_url(&self)  -> String;    // e.g. "http://0.0.0.0:9090"
}
```

### Drop Implementation

```rust
impl Drop for RedfishEventListener {
    fn drop(&mut self) {
        if let Some(handle) = self.join_handle.take() {
            handle.abort();   // cancel the axum server task
        }
    }
}
```

### Internal Thread Model

`start()` spawns an `axum` HTTP server as a `tokio::task`. The task handle
is stored in `join_handle`. On `stop()` or `Drop`, the handle is aborted.

Callbacks are stored in `Arc<Mutex<CallbackRegistry>>` so they can be
shared safely between the listener task and the registration methods.

---

## 16. Transport Layer — HttpClient

### Module: `transport/http_client.rs`
### Visibility: `pub(crate)`

```rust
pub(crate) struct HttpClient {
    client:   reqwest::Client,
    base_url: String,
    timeouts: TimeoutConfig,
}

impl HttpClient {
    pub(crate) fn new(base_url: &str, tls_config: TlsConfig, timeouts: TimeoutConfig)
        -> Result<Self, RedfishError>;

    // Async (primary)
    pub(crate) async fn request(
        &self,
        method:  &str,
        path:    &str,
        headers: HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError>;

    // Sync
    pub(crate) fn request_blocking(
        &self,
        method:  &str,
        path:    &str,
        headers: HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError>;
}
```

### RawHttpResponse (Internal)

```rust
pub(crate) struct RawHttpResponse {
    pub(crate) status_code: u16,
    pub(crate) headers:     HashMap<String, String>,
    pub(crate) body_text:   String,
    pub(crate) body_json:   Option<serde_json::Value>,
}
```

### Responsibilities

- Maintain a single `reqwest::Client` for connection reuse
- Attach standard Redfish headers to every request:
  `OData-Version: 4.0`, `Content-Type: application/json`, `Accept: application/json`
- Auth header attachment is **not** done here — done by `AuthManager`

---

## 17. Transport Layer — AuthManager

### Module: `transport/auth.rs`
### Visibility: `pub(crate)`

```rust
pub(crate) struct AuthManager<'a> {
    http_client: &'a HttpClient,
    credentials: Credentials,
    mode:        AuthMode,
}

impl<'a> AuthManager<'a> {
    pub(crate) async fn authenticate(&self) -> Result<AuthState, RedfishError>;
    pub(crate) fn authenticate_blocking(&self) -> Result<AuthState, RedfishError>;

    pub(crate) fn attach_auth(&self, state: &AuthState, headers: &mut HashMap<String, String>);

    pub(crate) async fn logout(&self, state: &AuthState) -> Result<(), RedfishError>;
    pub(crate) fn logout_blocking(&self, state: &AuthState) -> Result<(), RedfishError>;
}
```

### AuthState (Internal)

```rust
pub(crate) struct AuthState {
    pub(crate) mode:          AuthMode,
    pub(crate) session_token: Option<String>,
    pub(crate) session_uri:   Option<String>,
    pub(crate) credentials:   Credentials,
}
```

### Session Auth Flow

```
authenticate() — Session mode:
    POST {base_url}/redfish/v1/SessionService/Sessions
    body: {"UserName": ..., "Password": ...}
    → 201 Created
    → Extract X-Auth-Token header → session_token
    → Extract Location header → session_uri
    → Return AuthState
```

### Stateless Auth Flow

```
authenticate() — Stateless mode:
    GET {base_url}/redfish/v1
    with Basic Auth header
    → 200 OK (validates endpoint + credentials)
    → Return AuthState (credentials held for per-request attachment)
```

### Auth Attachment

```
attach_auth() — Session mode:
    headers.insert("X-Auth-Token", session_token)

attach_auth() — Stateless mode:
    let encoded = base64(username:password)
    headers.insert("Authorization", format!("Basic {encoded}"))
```

---

## 18. Transport Layer — TLS

### Module: `transport/tls.rs`
### Visibility: `pub(crate)`

```rust
pub(crate) struct TlsConfig {
    pub(crate) verify:       bool,
    pub(crate) ca_cert_path: Option<String>,
}

pub(crate) fn build_tls_config(config: &ConnectionConfig) -> TlsConfig;

pub(crate) fn apply_tls_to_builder(
    builder:    reqwest::ClientBuilder,
    tls_config: &TlsConfig,
) -> Result<reqwest::ClientBuilder, RedfishError>;
```

### Mapping from ConnectionConfig

| `ConnectionConfig` field | `TlsConfig` result |
|---|---|
| `verify_tls: true`, no CA cert | `verify: true`, `ca_cert_path: None` (system store) |
| `verify_tls: true`, `tls_ca_cert` set | `verify: true`, `ca_cert_path: Some(path)` |
| `verify_tls: false` | `verify: false` (dev/test only) |

---

## 19. Internal Data Contracts

Defined in `transport/mod.rs` or alongside the types that use them.
All `pub(crate)`.

### Credentials

```rust
#[derive(Clone)]
pub struct Credentials {
    pub username: String,
    pub password: String,
}
```

`Credentials` does not implement `Debug` — prevents accidental password
logging.

### EndpointCapabilities

```rust
pub(crate) struct EndpointCapabilities {
    pub(crate) redfish_version:    String,
    pub(crate) odata_version:      String,
    pub(crate) short_form:         bool,
    pub(crate) base_path:          String,
    pub(crate) available_services: Vec<String>,
}
```

### TimeoutConfig

```rust
pub(crate) struct TimeoutConfig {
    pub(crate) connect_secs:      f32,   // default: 10.0
    pub(crate) request_secs:      f32,   // default: 30.0
    pub(crate) task_poll_secs:    f32,   // default: 5.0
    pub(crate) task_timeout_secs: f32,   // default: 300.0
}
```

---

## 20. Error Design

### Error Enum

Defined in `lib.rs` (or `errors.rs`), re-exported publicly.

```rust
#[derive(Debug, thiserror::Error)]
pub enum RedfishError {
    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("TLS error: {0}")]
    TlsError(String),

    #[error("Authentication failed: {0}")]
    AuthFailed(String),

    #[error("Protocol error: {0}")]
    ProtocolError(String),

    #[error("HTTP error {status_code}: {message}")]
    HttpError { status_code: u16, message: String },

    #[error("Task timed out")]
    Timeout,

    #[error("Task failed: {0}")]
    TaskFailed(String),

    #[error("JSON parse error: {0}")]
    ParseError(String),
}
```

The `thiserror` crate is used for the `#[error]` derive. It is a dev
standard in the Rust ecosystem for library error types.

### What Returns Err vs What Returns Ok

| Situation | SDK Behaviour |
|---|---|
| Network failure | `Err(RedfishError::ConnectionFailed)` |
| TLS cert rejected | `Err(RedfishError::TlsError)` |
| 401 / 403 | `Err(RedfishError::AuthFailed)` |
| 404 | `Ok(RedfishResponse { success: false, status_code: 404, .. })` |
| Other 4xx / 5xx | `Ok(RedfishResponse { success: false, .. })` |
| 2xx | `Ok(RedfishResponse { success: true, .. })` |
| 202 | `Ok(RedfishResponse { task: Some(..), .. })` |
| Task timeout | `Err(RedfishError::Timeout)` |
| Task failed state | `Err(RedfishError::TaskFailed)` |

**404 is never an `Err`.** Same rule as Python and C++.

---

## 21. Async and Sync Model

### Pattern

All logic is written once as `async fn`. Sync `_blocking` variants drive
the async path using a `tokio::runtime::Runtime` stored inside
`ClientContext`.

```rust
// Async — all logic lives here
pub async fn get(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
    // ... full logic
}

// Sync — drives the async path, no duplicate logic
pub fn get_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
    self.runtime.block_on(self.get(uri))
}
```

The `runtime` field in `ClientContext` is an `Arc<tokio::runtime::Runtime>`.
It is created once at connect time and shared with service handles through
the context reference.

### Naming Convention

| Async variant | Sync variant |
|---|---|
| `connect(...)` | `connect_blocking(...)` |
| `get(uri)` | `get_blocking(uri)` |
| `subscribe(...)` | `subscribe_blocking(...)` |
| `full()` | `full_blocking()` |
| `wait(...)` | `wait_blocking(...)` |

---

## 22. Ownership and Lifetime Contracts

This section maps each architectural decision to its Rust enforcement.
No runtime checks are involved — all are compile-time.

| Contract | Enforcement |
|---|---|
| One connection per context | `ClientContext: !Clone` — compiler rejects copy |
| Context state is opaque | All `ClientContext` fields are private — compiler rejects direct access |
| Handles cannot outlive context | Lifetime `'ctx` on all handle types — compiler rejects dangling handles |
| Transport is internal | `transport` module is `pub(crate)` — callers cannot import it |
| Session token not leaked | `Credentials` does not implement `Debug` — does not appear in logs |
| Session closed on drop | `Drop` impl on `ClientContext` — fires automatically on scope exit |
| Listener independent lifecycle | Separate struct, not owned by `ClientContext` — compiler enforces no coupling |
| Callbacks are `Send + Sync + 'static` | Trait bounds on `on_event()` — required for `tokio::spawn` safety |

---

## 23. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — Rust design |
