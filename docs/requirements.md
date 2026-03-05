# Redfish Client SDK — Requirements Specification

**Document ID:** RSDK-REQ-001  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Glossary](#2-glossary)
3. [Stakeholders & Users](#3-stakeholders--users)
4. [Delivery Phases](#4-delivery-phases)
5. [Functional Requirements](#5-functional-requirements)
   - FR1 — Connection & Authentication
   - FR2 — Discovery
   - FR3 — REST Abstractions
   - FR4 — Task Management
   - FR5 — Event Service
   - FR6 — Log Service
   - FR7 — Update Service
   - FR8 — Telemetry Service
   - FR9 — Sample Clients
6. [Non-Functional Requirements](#6-non-functional-requirements)
   - NFR1 — Language & Packaging
   - NFR2 — Sync / Async
   - NFR3 — Concurrency Model
   - NFR4 — Error & Result Model
   - NFR5 — Endpoint Agnosticism
   - NFR6 — Security & Storage
   - NFR7 — Sample Client Quality
7. [Out of Scope](#7-out-of-scope)
8. [Requirements Traceability Matrix](#8-requirements-traceability-matrix)
9. [Change History](#9-change-history)

---

## 1. Purpose & Scope

The **Redfish Client SDK** is a linkable library that abstracts the DMTF Redfish
protocol, enabling client teams to build Redfish-capable applications without
implementing protocol-level concerns.

### Goals

- Provide a high-quality, well-documented SDK that accelerates adoption of
  Redfish across client teams
- Abstract common Redfish operations (discovery, REST, events, telemetry, logs,
  updates) behind clean, consistent APIs
- Support both **session-based** and **stateless** interaction models
- Be usable against **any standards-compliant Redfish endpoint** — real BMC
  hardware or simulators
- Be delivered in three language phases: **Python first**, then **C++**,
  then **Rust**

### Non-Goals

- The SDK does not implement BMC-side (server-side) logic
- The SDK does not manage credentials storage or audit logging
- The SDK does not abstract vendor-specific OEM extensions into typed models
- The SDK does not manage concurrency across multiple BMC connections

### Primary Integration Target (Development & Testing)

The SDK shall be developed and validated against the
**bmc-redfish-simulator** (`/home/hari/Tools/bmc-redfish-simulator`)
and the **AMD Platform mockup** (`/home/hari/mockup/AMD_Platform_v3`).
However, the SDK shall make no assumptions specific to this simulator —
it shall work against any compliant Redfish endpoint.

---

## 2. Glossary

| Term | Definition |
|---|---|
| **BMC** | Baseboard Management Controller — the hardware management processor on a server |
| **Redfish** | DMTF standard REST-based management API for servers and infrastructure |
| **ServiceRoot** | The entry point of every Redfish service (`/redfish/v1`) |
| **Session Mode** | Auth model where a session token is established once and reused |
| **Stateless Mode** | Auth model where each request carries its own credentials |
| **SSE** | Server-Sent Events — a protocol for streaming events from server to client |
| **Task** | A Redfish resource representing a long-running asynchronous operation |
| **OEM** | Vendor-specific extensions to Redfish beyond the DMTF standard |
| **Discovery** | The act of traversing ServiceRoot to enumerate available services and resources |
| **Message Registry** | A DMTF-defined file mapping MessageId codes to human-readable messages |
| **CPER** | Common Platform Error Record — binary format for hardware error reporting |
| **pybind11** | C++ library for creating Python bindings of C++ code |

---

## 3. Stakeholders & Users

| Role | Description | Primary SDK Usage |
|---|---|---|
| **BMC Developers** | Firmware/platform engineers building BMC management software | C++ SDK (Phase 2) — typed abstractions and direct APIs |
| **Test / QA Engineers** | Automation engineers validating BMC features | Python SDK (Phase 1) — quick test scripts against simulator |
| **Platform Integration Teams** | Teams integrating server management into broader systems | Python and C++ SDK — event monitoring, telemetry, discovery |
| **Systems Engineers** | Advanced users who know the Redfish schema well | Direct/raw APIs across all languages |

---

## 4. Delivery Phases

The SDK shall be delivered in three sequential phases. Each phase delivers a
**complete, standalone SDK** in a different language. The Python Phase 1 API
surface shall serve as the **design reference** for subsequent phases.

```
Phase 1 — Python SDK        (Initial delivery)
Phase 2 — C++ SDK           (After Python SDK is validated)
Phase 3 — Rust SDK          (After team is aligned to Rust)
```

### Phase 1 — Python SDK

- Pure Python package, installable via `pip`
- Uses `httpx` for sync and async HTTP transport
- Uses `asyncio` for async programming model
- Uses `pydantic` for response models and schema validation
- Full type hints throughout — API surface is explicit
- All functional requirements FR1–FR9 implemented
- Validated against bmc-redfish-simulator

### Phase 2 — C++ SDK

- C++20 library (static `.a` and shared `.so`/`.dll`)
- Same API surface and behaviour as proven in Phase 1
- Uses `libcurl` (sync) and `cpp-httplib` or `Boost.Beast` (async)
- Uses `nlohmann/json` for JSON handling
- C++20 coroutines for async model
- Exposes a clean `extern "C"` surface for future Rust FFI
- CMake build system

### Phase 3 — Rust SDK

- Idiomatic Rust — not an FFI wrapper over C++
- Uses `reqwest` + `tokio` for async HTTP
- Uses `serde_json` for JSON handling
- Same API concepts and behaviour as Phase 1 and Phase 2
- Rust team readiness is a prerequisite for this phase

---

## 5. Functional Requirements

### FR1 — Connection & Authentication

| ID | Priority | Requirement |
|---|---|---|
| FR1.1 | MUST | SDK shall support **Session-based authentication** — the client establishes a Redfish session (`POST /redfish/v1/SessionService/Sessions`), and the SDK manages the session token for its lifetime |
| FR1.2 | MUST | SDK shall support **Stateless / discrete command mode** — each call carries its own credentials (Basic Auth), no session state is held by the SDK |
| FR1.3 | MUST | The authentication model (session vs. stateless) shall be a **caller choice at connection time**, not a compile-time or configuration-time decision |
| FR1.4 | MUST | SDK shall support HTTPS with **strict TLS certificate validation** |
| FR1.5 | MUST | SDK shall support **TLS certificate bypass** for development and test scenarios involving self-signed certificates |
| FR1.6 | MUST | SDK shall support configurable **connection timeout** and **request timeout** |
| FR1.7 | SHOULD | SDK shall support **session keep-alive** — caller can choose to maintain an active session across multiple operations |
| FR1.8 | SHOULD | SDK shall support configurable **retry on connection failure** — caller specifies retry count and delay between attempts |
| FR1.9 | SHOULD | SDK shall support configurable **retry on specific HTTP status codes** (e.g. 503, 429) — caller specifies list of status codes, retry count, and delay |
| FR1.10 | SHOULD | SDK shall support **in-place session refresh** — renew the auth token on the existing client context without tearing down and reconnecting |

---

### FR2 — Discovery

| ID | Priority | Requirement |
|---|---|---|
| FR2.1 | MUST | SDK shall provide **Full Discovery** — traverse ServiceRoot and enumerate all available top-level services, their capabilities, and accessible resource collections |
| FR2.2 | MUST | SDK shall provide **Partial Discovery** — caller can discover a specific top-level node only (e.g., only `EventService`, only `TelemetryService`, only `Systems`) |
| FR2.3 | MUST | SDK shall provide **Root-level Discovery** — enumerate only what is directly linked from ServiceRoot without deep traversal |
| FR2.4 | MUST | Discovery shall be **runtime-driven** — derived entirely from what the connected endpoint actually exposes, with no client-side assumptions about schema versions or resource availability |
| FR2.5 | MUST | Discovery results shall expose what **services, capabilities, and resource collections** are available on the connected endpoint |
| FR2.6 | MUST | Discovery results shall be **inspectable** — caller can query whether a specific service or capability is present before calling it |
| FR2.7 | SHOULD | SDK shall provide a **local schema bundle** as fallback for air-gapped environments where the BMC cannot serve schemas |

---

### FR3 — REST Abstractions

| ID | Priority | Requirement |
|---|---|---|
| FR3.1 | MUST | SDK shall provide abstracted **GET** operation — fetch any Redfish resource by URI |
| FR3.2 | MUST | SDK shall provide abstracted **POST** operation — create resources or invoke actions |
| FR3.3 | MUST | SDK shall provide abstracted **PATCH** operation — update resource properties |
| FR3.4 | MUST | SDK shall provide abstracted **DELETE** operation — remove resources |
| FR3.5 | MUST | All REST abstractions shall handle HTTP-level concerns transparently — `OData-Version` headers, `Content-Type` negotiation, `ETag` handling |
| FR3.6 | MUST | SDK shall provide **direct / raw APIs** — advanced callers can call any URI with full control over request body and headers, bypassing typed abstractions |
| FR3.7 | MUST | OEM extension endpoints shall **always** be accessed via raw/basic APIs — typed abstractions shall not attempt to model OEM resources |
| FR3.8 | MUST | SDK shall return a **RedfishResponse** object for all calls, carrying HTTP status code, headers, response body, and any Redfish extended error information |

---

### FR4 — Task Management

| ID | Priority | Requirement |
|---|---|---|
| FR4.1 | MUST | SDK shall automatically detect and handle **202 Accepted** responses — expose a `RedfishTask` handle to the caller |
| FR4.2 | MUST | SDK shall provide **synchronous task wait** — block the caller until the task reaches a terminal state or timeout expires |
| FR4.3 | MUST | SDK shall provide **asynchronous task monitoring** — caller registers a callback that is invoked when task state changes |
| FR4.4 | MUST | Task **polling interval** and **timeout** shall be caller-configurable |
| FR4.5 | SHOULD | SDK shall support **task cancellation** via DELETE on the Task resource, where the BMC supports it |
| FR4.6 | MUST | `RedfishTask` handle shall expose task state, progress percentage, and any messages returned by the BMC |

---

### FR5 — Event Service

| ID | Priority | Requirement |
|---|---|---|
| FR5.1 | MUST | SDK shall provide **Event Subscription APIs** — register a new subscription on the BMC (`POST /redfish/v1/EventService/Subscriptions`).  The subscription API shall accept `RegistryPrefixes`, `MessageIds`, `EventTypes`, `ResourceTypes`, and `EventFormatType` fields so that callers can match the subscription body required by real BMC endpoints |
| FR5.2 | MUST | SDK shall provide APIs to **list, modify, and delete** existing event subscriptions |
| FR5.3 | MUST | SDK shall provide a built-in **Redfish Event Listener** — an embedded HTTP(S) server capable of receiving push event deliveries from the BMC.  The listener shall: (a) validate the `Context` field in incoming events against the subscription context if one was configured, returning `204 No Content` without firing callbacks on mismatch; (b) log the latency between the event's `EventTimestamp` and the reception time; (c) track a per-source-IP event counter; (d) buffer the most recent N events for retrieval via `GET` on the listener path |
| FR5.4 | MUST | SDK shall provide **Event Monitoring APIs** — caller registers callbacks that are invoked when events arrive at the listener |
| FR5.5 | MUST | SDK shall support **SSE (Server-Sent Events)** subscription type — open a streaming connection to the BMC and receive events as they are emitted |
| FR5.6 | MUST | SDK shall support **Message Registry decoding** — resolve a `MessageId` to a human-readable message and arguments using the registry fetched from the BMC |
| FR5.7 | MUST | Both **synchronous and asynchronous** modes shall be supported for event delivery and callback invocation |
| FR5.8 | SHOULD | SDK shall support filtering of received events by `MessageId`, `RegistryPrefix`, `EventType`, and `OriginOfCondition` |
| FR5.9 | SHOULD | SDK shall provide a **Submit Test Event API** — POST to `/redfish/v1/EventService/Actions/EventService.SubmitTestEvent` — to allow callers to inject a synthetic event for testing subscription pipelines without requiring live BMC activity |

---

### FR6 — Log Service

| ID | Priority | Requirement |
|---|---|---|
| FR6.1 | MUST | SDK shall provide APIs to **read log entries** from any `LogService` resource on the BMC |
| FR6.2 | MUST | SDK shall support **filtering** of log entries by severity, time range, and message ID |
| FR6.3 | MUST | SDK shall provide APIs to **clear logs** (`POST LogService/Actions/LogService.ClearLog`) where the BMC supports it |
| FR6.4 | MUST | SDK shall support **multiple log services** on a single BMC — e.g., System EventLog, Manager logs, CPERLogs — accessible by URI or by discovery |
| FR6.5 | SHOULD | SDK shall support **pagination** of log entry collections for BMCs that implement `Members@odata.nextLink` |
| FR6.6 | COULD | SDK shall provide **typed binary log entry parsing** for known vendor formats (IPMI SEL records) — extracting record type, manufacturer ID, event ID, and platform-specific fields from raw hex data.  Two input formats shall be accepted: (a) the OpenBMC-prefixed form `"Raw Data : Hex <hex>"` as found in `LogEntry.MessageArgs[0]`; (b) the flat generator form `"Raw data: <hex>"` (lowercase, no "Hex" keyword) as emitted by event generator tooling that replays `SELRawText.txt` files |

---

### FR7 — Update Service

| ID | Priority | Requirement |
|---|---|---|
| FR7.1 | MUST | SDK shall provide APIs to **query firmware inventory** (`GET UpdateService/FirmwareInventory`) |
| FR7.2 | MUST | SDK shall provide APIs to **query software inventory** (`GET UpdateService/SoftwareInventory`) |
| FR7.3 | MUST | SDK shall provide APIs to **initiate firmware updates** via the `SimpleUpdate` action |
| FR7.4 | MUST | Update operations that return Tasks shall be automatically handled via the Task Management APIs (FR4) |
| FR7.5 | SHOULD | SDK shall support **multipart firmware upload** — stream a local firmware image file directly to the BMC UpdateService URI, in addition to the URI-based `SimpleUpdate` action |

---

### FR8 — Telemetry Service

| ID | Priority | Requirement |
|---|---|---|
| FR8.1 | MUST | SDK shall provide APIs to **query Metric Report Definitions** (`GET TelemetryService/MetricReportDefinitions`) |
| FR8.2 | MUST | SDK shall provide APIs to **read Metric Reports** (`GET TelemetryService/MetricReports`) |
| FR8.3 | MUST | SDK shall provide APIs to **subscribe to Metric Report updates** via the Event Service (FR5) |
| FR8.4 | SHOULD | SDK shall support **SSE-based streaming telemetry** for real-time metric delivery |

---

### FR9 — Sample Clients

| ID | Priority | Requirement |
|---|---|---|
| FR9.1 | MUST | SDK shall ship **runnable sample clients** in each supported language demonstrating each major feature area |
| FR9.2 | MUST | All samples shall be **self-contained and executable** — a developer shall be able to clone, build/run, and see results with minimal setup |
| FR9.3 | MUST | Samples shall target the **bmc-redfish-simulator** by default so they run without real hardware |
| FR9.4 | MUST | Samples shall be configurable via **command-line arguments** (`--host`, `--port`, `--user`, `--password`) so they can point at real BMC hardware without code changes |
| FR9.5 | MUST | Each sample shall demonstrate **one focused feature** — not a monolithic demonstration |

#### Required Sample Coverage

| Sample ID | Feature Demonstrated |
|---|---|
| `01_connect_discover` | Connect, authenticate, full ServiceRoot discovery |
| `02_partial_discover` | Partial discovery — single service node only |
| `03_get_resources` | GET Systems, Chassis, Managers with typed access |
| `04_direct_api` | Raw/direct GET and POST — advanced user mode |
| `05_event_subscribe` | Register an event subscription on the BMC |
| `06_event_listener` | Start the event listener, receive and print events |
| `07_event_monitor` | Subscribe + listen + callback in one integrated flow |
| `08_log_service` | Query logs, filter by severity, clear logs |
| `09_telemetry` | Query metric definitions and read metric reports |
| `10_update_service` | Query firmware inventory, trigger SimpleUpdate |
| `11_task_polling` | Async task monitor — wait for long-running operation |
| `12_session_vs_stateless` | Side-by-side session mode vs. discrete command mode |

---

## 6. Non-Functional Requirements

### NFR1 — Language & Packaging

| ID | Priority | Requirement |
|---|---|---|
| NFR1.1 | MUST | **Phase 1:** SDK shall be implemented as a **pure Python package**, installable via `pip` with a `pyproject.toml` |
| NFR1.2 | MUST | **Phase 2:** SDK shall be implemented as a **C++20 library** (static and shared), built with CMake |
| NFR1.3 | MUST | **Phase 3:** SDK shall be implemented as an **idiomatic Rust crate**, published to crates.io |
| NFR1.4 | MUST | Each language implementation shall be a **first-class, idiomatic** implementation — not a binding or wrapper over another language's implementation |
| NFR1.5 | MUST | **API design consistency** shall be maintained across all three languages — same concepts, same naming conventions, same observable behaviour |
| NFR1.6 | MUST | The **Python Phase 1 implementation shall serve as the API design reference** for C++ (Phase 2) and Rust (Phase 3) |
| NFR1.7 | MUST | The C++ SDK shall expose a clean `extern "C"` surface to enable Rust FFI bindings as a future option |

---

### NFR2 — Sync / Async

| ID | Priority | Requirement |
|---|---|---|
| NFR2.1 | MUST | All SDK APIs shall be available in both **synchronous and asynchronous** variants |
| NFR2.2 | MUST | **Python:** Async implementation shall use `asyncio` / `httpx` async client; sync shall be a thin wrapper |
| NFR2.3 | MUST | **C++:** Async implementation shall use C++20 coroutines (`co_await`); sync shall drive the async core to completion |
| NFR2.4 | MUST | **Rust:** Async implementation shall use `tokio`; sync shall use `tokio::Runtime::block_on` |
| NFR2.5 | MUST | The caller shall choose sync or async per call — not per client instance |

---

### NFR3 — Concurrency Model

| ID | Priority | Requirement |
|---|---|---|
| NFR3.1 | MUST | The SDK shall be **single-connection** per client instance — no internal connection pooling |
| NFR3.2 | MUST | **Concurrency across multiple BMC connections** shall be entirely the caller's responsibility — the SDK shall not manage it |
| NFR3.3 | MUST | SDK internals shall be **thread-safe for concurrent read operations** (GET) on the same client instance |
| NFR3.4 | MUST | The SDK shall **not** create or manage background threads internally, with the exception of the Event Listener server (FR5.3) which requires its own I/O loop |

---

### NFR4 — Error & Result Model

| ID | Priority | Requirement |
|---|---|---|
| NFR4.1 | MUST | SDK shall surface errors at the **Redfish protocol level only** — HTTP status codes, Redfish `@Message.ExtendedInfo` payloads, and network-level failures |
| NFR4.2 | MUST | SDK shall **not** dictate how callers handle errors — no forced exception model or mandatory result-code pattern is imposed |
| NFR4.3 | MUST | SDK shall provide a **`RedfishResponse`** type for all operations, carrying: HTTP status code, response headers, response body (raw JSON), and any Redfish extended error information |
| NFR4.4 | MUST | The `RedfishResponse` type shall allow the caller to inspect success/failure and access error details without having to parse raw HTTP |

---

### NFR5 — Endpoint Agnosticism

| ID | Priority | Requirement |
|---|---|---|
| NFR5.1 | MUST | SDK shall work against **any standards-compliant Redfish endpoint** — real BMC hardware or simulator |
| NFR5.2 | MUST | **Unknown fields** in BMC responses shall be preserved and accessible to the caller — not silently discarded |
| NFR5.3 | MUST | **Missing optional resources** shall return empty results — not errors or exceptions |
| NFR5.4 | MUST | **OEM namespaces** in responses shall not cause failures in standard API paths |
| NFR5.5 | MUST | SDK shall support both standard path form (`/redfish/v1/...`) and **short-form** paths — auto-detected from the endpoint at connect time |

---

### NFR6 — Security & Storage

| ID | Priority | Requirement |
|---|---|---|
| NFR6.1 | MUST | SDK shall **not** implement credential storage of any kind — credentials are passed by the caller per connection and not persisted |
| NFR6.2 | MUST | SDK shall **not** implement audit logging — callers may wrap SDK calls to add audit capability |
| NFR6.3 | MUST | Session tokens shall be held **in-memory only** for the duration of the session and not written to any storage medium by the SDK |
| NFR6.4 | MUST | SDK shall **not** dictate or enforce any storage policy — that is entirely the caller's domain |

---

### NFR7 — Sample Client Quality

| ID | Priority | Requirement |
|---|---|---|
| NFR7.1 | MUST | Samples shall include **inline comments** explaining what each SDK call does and why |
| NFR7.2 | MUST | Each sample group shall have a `README` explaining prerequisites, how to start the simulator, and how to run each sample |
| NFR7.3 | MUST | Python samples shall be runnable with a **single command**: `python samples/01_connect_discover.py --host 127.0.0.1 --port 8000` |
| NFR7.4 | MUST | C++ samples shall be buildable via the **same CMake build** as the SDK itself — no separate build configuration |
| NFR7.5 | SHOULD | Samples shall demonstrate both **sync and async** variants where the feature supports it |

---

### NFR8 — Observability & Testability

| ID | Priority | Requirement |
|---|---|---|
| NFR8.1 | MUST | SDK shall instrument all transport and service operations with **structured log calls** using a standard observability interface (`tracing` in Rust, `logging` in Python, structured output in C++) — the SDK shall never configure a log handler itself; callers opt in by installing their own subscriber or handler |
| NFR8.2 | MUST | The **transport layer shall be testable without a live endpoint** — each language shall provide a mock/injectable transport interface so unit tests run without a running BMC or simulator |

---

## 7. Out of Scope (Initial Release)

The following items are explicitly **not in scope** for any phase of this SDK:

| Item | Reason |
|---|---|
| CPER / libcper decoding | Belongs in a separate `redfish-ras` extension module |
| Vendor-specific OEM typed models | OEM access is via raw/basic APIs only |
| SSDP discovery | Out of scope for client SDK |
| Internal connection pooling | Concurrency is caller's responsibility (NFR3) |
| Credential storage or secrets management | Caller's responsibility (NFR6) |
| Audit logging | Caller's responsibility (NFR6) |
| Rust bindings via FFI (Phase 1 & 2) | Phase 3 is idiomatic Rust, not FFI |
| WebSocket-based eventing | SSE is the supported streaming model |
| Redfish Aggregation Service client | Future consideration |

---

## 8. Requirements Traceability Matrix

| Requirement | Phase 1 (Python) | Phase 2 (C++) | Phase 3 (Rust) |
|---|---|---|---|
| FR1 — Connection & Auth | ✅ | ✅ | ✅ |
| FR2 — Discovery | ✅ | ✅ | ✅ |
| FR3 — REST Abstractions | ✅ | ✅ | ✅ |
| FR4 — Task Management | ✅ | ✅ | ✅ |
| FR5 — Event Service | ✅ | ✅ | ✅ |
| FR6 — Log Service | ✅ | ✅ | ✅ |
| FR7 — Update Service | ✅ | ✅ | ✅ |
| FR8 — Telemetry Service | ✅ | ✅ | ✅ |
| FR9 — Sample Clients | ✅ Python | ✅ C++ | ✅ Rust |
| NFR1 — Language & Packaging | Python / pip | C++20 / CMake | Rust / cargo |
| NFR2 — Sync / Async | asyncio / httpx | C++20 coroutines | tokio |
| NFR3 — Concurrency Model | ✅ | ✅ | ✅ |
| NFR4 — Error & Result Model | ✅ | ✅ | ✅ |
| NFR5 — Endpoint Agnosticism | ✅ | ✅ | ✅ |
| NFR6 — Security & Storage | ✅ | ✅ | ✅ |
| NFR7 — Sample Quality | ✅ | ✅ | ✅ |
| NFR8 — Observability & Testability | ✅ | ✅ | ✅ |

---

## 9. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — requirements captured from design discussion |
| 0.2 | 2026-03-05 | Copilot | Added FR1.8–FR1.10 (retry, auth refresh), FR6.6 (SEL parsing), FR7.5 (multipart upload), NFR8 (observability & testability) — informed by team Rust client analysis |
| 0.3 | 2026-03-07 | Copilot | FR5.1 extended with `ResourceTypes` + `EventFormatType` subscription fields; FR5.3 extended with context validation, latency logging, per-IP event count, buffered GET; FR5.9 added (SubmitTestEvent); FR6.6 extended to cover flat generator SEL format (`"Raw data: <hex>"`) — all informed by EventMockupServerToolKit analysis |
