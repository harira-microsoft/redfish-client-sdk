# Redfish Client SDK — Rust Architecture

**Document ID:** RSDK-ARCH-004  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Base Architecture:** RSDK-ARCH-001  
**API Reference:** RSDK-ARCH-002 (Python), RSDK-ARCH-003 (C++)  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Rust-Specific Architectural Goals](#2-rust-specific-architectural-goals)
3. [Technology Choices](#3-technology-choices)
4. [Crate Structure](#4-crate-structure)
5. [Component Expression in Rust](#5-component-expression-in-rust)
6. [Async and Sync Model in Rust](#6-async-and-sync-model-in-rust)
7. [ClientContext in Rust](#7-clientcontext-in-rust)
8. [RedfishResponse in Rust](#8-redfishresponse-in-rust)
9. [Event Listener in Rust](#9-event-listener-in-rust)
10. [Ownership and Lifetime Model](#10-ownership-and-lifetime-model)
11. [Build and Distribution](#11-build-and-distribution)
12. [Change History](#12-change-history)

---

## 1. Purpose

This document defines the Rust architecture for Phase 3 of the Redfish
Client SDK. It takes the language-independent architecture (RSDK-ARCH-001)
as its foundation, uses the Python (RSDK-ARCH-002) and C++ (RSDK-ARCH-003)
designs as behavioral references, and expresses every component and
decision idiomatically in Rust.

The Rust implementation is the **Phase 3 delivery** — built after the
C++ SDK is validated. It is a **first-class idiomatic Rust crate** — not
an FFI wrapper over the C++ library.

### Prerequisite

Phase 3 begins only when the team is aligned and trained on Rust. The
architecture is documented now so that:
- The design is thought through before training begins
- The team has an architectural reference during the learning process
- The Phase 1 and Phase 2 API surfaces can be validated against this
  architecture for consistency

---

## 2. Rust-Specific Architectural Goals

| Goal | Rationale |
|---|---|
| Idiomatic Rust — not a C++ port | Rust callers deserve a native experience, not a translation |
| Async-first with `tokio` | The standard async runtime for Rust networking |
| Ownership expresses connection lifecycle | Rust's ownership model enforces one-connection-per-context naturally |
| `Result<T, RedfishError>` for all fallible operations | Idiomatic Rust error handling |
| Traits for extensibility | Allows callers to mock, test, or extend SDK components cleanly |
| Publishable to crates.io | Standard Rust distribution |

---

## 3. Technology Choices

### Core Dependencies

| Concern | Crate | Reason |
|---|---|---|
| HTTP transport (async) | `reqwest` | High-level, async, excellent TLS support |
| HTTP transport (sync) | `reqwest` (blocking feature) | Same crate, blocking mode |
| Async runtime | `tokio` | Standard async runtime for Rust networking |
| JSON parsing | `serde_json` | Standard for Rust JSON |
| Serialization / deserialization | `serde` | Standard for Rust data modelling |
| TLS | `rustls` or `native-tls` | `rustls` for pure Rust; `native-tls` for platform TLS |
| Event Listener server | `axum` (built on `tokio` + `hyper`) | Lightweight, idiomatic async HTTP server |

### Development / Build Dependencies

| Concern | Crate / Tool | Reason |
|---|---|---|
| Build system | `cargo` | Standard Rust build tool |
| Testing | `cargo test` + `tokio::test` | Built in — async test support via tokio |
| Documentation | `cargo doc` | Standard Rust doc generation |
| Linting | `clippy` | Standard Rust linter |
| Publishing | `crates.io` | Standard Rust distribution |

---

## 4. Crate Structure

```
RedfishClientSDK/
└── rust/
    ├── Cargo.toml                      # Workspace manifest
    ├── Cargo.lock
    │
    ├── redfish-sdk/                    # Main library crate
    │   ├── Cargo.toml
    │   └── src/
    │       ├── lib.rs                  # Crate root — public API exports
    │       ├── client.rs               # connect() function
    │       ├── context.rs              # ClientContext
    │       │
    │       ├── discovery/
    │       │   ├── mod.rs
    │       │   └── discovery.rs
    │       │
    │       ├── services/
    │       │   ├── mod.rs
    │       │   ├── event_service.rs
    │       │   ├── log_service.rs
    │       │   ├── telemetry_service.rs
    │       │   └── update_service.rs
    │       │
    │       ├── events/
    │       │   ├── mod.rs
    │       │   └── listener.rs         # RedfishEventListener
    │       │
    │       ├── protocol/
    │       │   ├── mod.rs
    │       │   ├── response.rs         # RedfishResponse
    │       │   ├── task.rs             # RedfishTask and TaskManager
    │       │   └── registry.rs         # MessageRegistry
    │       │
    │       └── transport/
    │           ├── mod.rs
    │           ├── http_client.rs      # reqwest wrapper
    │           ├── auth.rs             # AuthManager
    │           └── tls.rs              # TLS configuration
    │
    └── samples/                        # Runnable sample binaries
        ├── Cargo.toml
        └── src/
            ├── bin/
            │   ├── 01_connect_discover.rs
            │   ├── 02_partial_discover.rs
            │   ├── 03_get_resources.rs
            │   ├── 04_direct_api.rs
            │   ├── 05_event_subscribe.rs
            │   ├── 06_event_listener.rs
            │   ├── 07_event_monitor.rs
            │   ├── 08_log_service.rs
            │   ├── 09_telemetry.rs
            │   ├── 10_update_service.rs
            │   ├── 11_task_polling.rs
            │   └── 12_session_vs_stateless.rs
            └── README.md
```

---

## 5. Component Expression in Rust

### SDK Entry Point → `client.rs`

A free async function `connect()` in the `redfish_sdk` crate root.
Two variants:

- `async fn connect(params) -> Result<ClientContext, RedfishError>` — async
- `fn connect_blocking(params) -> Result<ClientContext, RedfishError>` — sync,
  uses `tokio::runtime::Runtime::block_on` internally

The caller never constructs a `ClientContext` directly.

---

### ClientContext → `context.rs`

A struct with private fields. All fields are private — inaccessible
to callers directly. The struct owns the connection state.

Rust's ownership model naturally enforces the single-connection-per-context
semantic — the context is **not Clone**. It can be moved. When it is
dropped, the connection is closed (via the `Drop` trait).

The context exposes service access methods that return lightweight
handle structs borrowing from the context:

- `ctx.event_service()` — returns `EventServiceHandle<'_>`
- `ctx.log_service()` — returns `LogServiceHandle<'_>`
- `ctx.telemetry_service()` — returns `TelemetryServiceHandle<'_>`
- `ctx.update_service()` — returns `UpdateServiceHandle<'_>`
- `ctx.discovery()` — returns `Discovery<'_>`

The lifetime `'_` ties the handle's lifetime to the context. Handles
cannot outlive the context. This is enforced by the compiler — no
runtime checks needed.

---

### Service Handles

Lightweight structs with a lifetime parameter borrowing from the context.
They expose intent-driven async methods returning
`Result<RedfishResponse, RedfishError>`.

Each method has an async variant (primary) and a blocking sync variant
(suffixed with `_blocking`).

---

### Discovery → `discovery/discovery.rs`

Accessed via `ctx.discovery()`. Three async methods:

- `full() -> Result<DiscoveryResult, RedfishError>`
- `partial(service) -> Result<DiscoveryResult, RedfishError>`
- `root() -> Result<DiscoveryResult, RedfishError>`

`DiscoveryResult` is a struct with query methods:
- `has_service(name) -> bool`
- `service_uri(name) -> Option<&str>`

---

### Protocol Layer → `protocol/`

Three modules, all private:

- `response.rs` — `RedfishResponse` as a Rust struct with derived `serde`
- `task.rs` — `RedfishTask` handle and async `TaskManager`
- `registry.rs` — `MessageRegistry` with async fetch and local cache

---

### Transport Layer → `transport/`

Private modules wrapping `reqwest`:

- `http_client.rs` — wraps `reqwest::Client`, provides uniform internal
  async request interface
- `auth.rs` — implements session and stateless auth flows
- `tls.rs` — builds `reqwest::ClientBuilder` TLS config

---

### Event Listener → `events/listener.rs`

A standalone struct `RedfishEventListener`. Built on `axum` running on
its own `tokio` runtime (spawned on a dedicated thread — the one exception
to NFR3.4, same as C++).

Callback registration uses Rust closures or trait objects:

```
listener.on_event(|event: RedfishEvent| async move {
    // handle event
})
```

---

## 6. Async and Sync Model in Rust

### The Pattern

All business logic lives in async functions. `tokio` is the runtime.
Sync variants use `tokio::runtime::Runtime::block_on` to drive async
to completion.

```
Primary:  async fn get(&self, uri: &str) -> Result<RedfishResponse, RedfishError>
Sync:     fn get_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError>
```

### Naming Convention

Mirrors Python and C++ conventions for cross-language consistency:

| Async variant | Sync variant |
|---|---|
| `get(uri)` — async | `get_blocking(uri)` — sync |
| `connect(params)` — async | `connect_blocking(params)` — sync |
| `subscribe(...)` — async | `subscribe_blocking(...)` — sync |

---

## 7. ClientContext in Rust

### Struct Definition (Conceptual — private fields)

```
pub struct ClientContext {
    // All fields private
    http_client:    transport::HttpClient,
    auth_state:     transport::AuthState,
    capabilities:   EndpointCapabilities,
    schema_cache:   HashMap<String, serde_json::Value>,
    discovery_map:  HashMap<String, String>,
    config:         ConnectionConfig,
}
```

### Ownership Semantics

| Property | Behavior |
|---|---|
| `Clone` | Not implemented — one context per connection |
| `Send` | Implemented — context can be moved across thread boundaries |
| `Sync` | Not implemented — concurrent use from multiple threads not supported |
| `Drop` | Implemented — closes session, releases transport on drop |

### Multiple BMC Connections

```rust
let ctx1 = redfish_sdk::connect(params1).await?;
let ctx2 = redfish_sdk::connect(params2).await?;
// Both live independently — Rust ownership ensures no aliasing
```

---

## 8. RedfishResponse in Rust

A struct with derived `serde::Deserialize` and `Debug`. Value type —
owned, not borrowed.

### Fields

| Field | Type | Description |
|---|---|---|
| `status_code` | `u16` | HTTP status code |
| `success` | `bool` | True if status_code is 2xx |
| `headers` | `HashMap<String, String>` | Response headers |
| `body` | `Option<serde_json::Value>` | Parsed JSON body |
| `extended_info` | `Vec<RedfishMessage>` | Extended error info |
| `task` | `Option<RedfishTask>` | Present only on 202 responses |
| `raw` | `String` | Raw response body |

### RedfishMessage (nested struct)

| Field | Type | Description |
|---|---|---|
| `message_id` | `String` | DMTF MessageId |
| `message` | `String` | Human-readable text |
| `severity` | `String` | OK / Warning / Critical |
| `resolution` | `Option<String>` | Resolution if provided |

### RedfishError (Error Type)

A Rust enum covering all SDK-level error variants:

| Variant | When |
|---|---|
| `ConnectionFailed(String)` | TCP/TLS connection could not be established |
| `AuthFailed(String)` | Authentication was rejected by the BMC |
| `HttpError(u16, String)` | BMC returned a non-2xx, non-202 response |
| `ParseError(String)` | Response body could not be parsed as JSON |
| `TaskFailed(String)` | A polled task reached a failed terminal state |
| `Timeout` | Request or task polling exceeded configured timeout |

---

## 9. Event Listener in Rust

### Lifecycle

```rust
let mut listener = RedfishEventListener::new(9090);
listener.use_context(&ctx);
listener.on_event(|event| async move {
    println!("Received: {:?}", event);
});
listener.start().await?;
// ...
listener.stop().await;
```

`RedfishEventListener` spawns a `tokio` task for the `axum` server.
It holds a `JoinHandle` and cancels it on `stop()` or on `Drop`.

---

## 10. Ownership and Lifetime Model

Rust's ownership and lifetime system enforces the architectural decisions
from RSDK-ARCH-001 at compile time — not at runtime:

| Architectural Decision | Rust Enforcement |
|---|---|
| AD3 — Context is opaque | Private fields — compiler rejects direct access |
| AD3 — One connection per context | `!Clone` — compiler rejects copying |
| AD4 — Transport is internal | `transport` module is `pub(crate)` only |
| AD7 — Listener independent lifecycle | Separate struct, not owned by context |
| Handles cannot outlive context | Lifetime parameter `'_` — compiler enforced |
| Session token not persisted | Held in `AuthState` — dropped with context |

This is the key advantage of the Rust implementation: **architectural
invariants are enforced by the compiler**, not by developer discipline.

---

## 11. Build and Distribution

### Cargo.toml (key fields)

```toml
[package]
name = "redfish-sdk"
version = "0.1.0"
edition = "2021"
rust-version = "1.75"

[dependencies]
reqwest = { version = "0.11", features = ["json", "rustls-tls"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
axum = "0.7"
```

### Build and Test

```bash
cargo build --release
cargo test
cargo doc --open
```

### Run a Sample

```bash
cargo run --bin 01_connect_discover -- --host 127.0.0.1 --port 8000
```

### Publish

```bash
cargo publish
```

---

## 12. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — Rust architecture |
