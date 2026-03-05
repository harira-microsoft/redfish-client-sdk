# Redfish Client SDK — C++ Design

**Document ID:** RSDK-DESIGN-002  
**Version:** 0.2  
**Status:** Locked  
**Date:** March 6, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Architecture Ref:** RSDK-ARCH-001, RSDK-ARCH-003  
**API Reference:** RSDK-DESIGN-001 (Python)  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Design Principles](#2-design-principles)
3. [Header / Source Dependency Map](#3-header--source-dependency-map)
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
22. [extern "C" Surface](#22-extern-c-surface)
23. [Change History](#23-change-history)

---

## 1. Purpose

This document defines the detailed design of the C++ SDK (Phase 2). It mirrors
the Python design (RSDK-DESIGN-001) in structure and API surface, expressed
idiomatically in C++20.

A developer assigned to any component can start from this document without
making design decisions.

**API parity with Python is the primary goal.** Feature behaviour is identical.
Only idioms differ.

---

## 2. Design Principles

| Principle | C++ Expression |
|---|---|
| One entry point | `redfish::connect()` free function — callers never construct `ClientContext` directly |
| Opaque handle | `ClientContext` uses Pimpl — no internal state visible in the public header |
| Move-only context | `ClientContext` is move-only — one owner enforced at compile time |
| Async-first | All logic lives in `_async` coroutines; sync variants drive them |
| RAII | `ClientContext` destructor closes session; `RedfishEventListener` destructor stops server |
| Uniform response | Every public method returns `RedfishResponse` |
| No caller state management | Session token, schema cache, discovery map live inside `ClientContext::Impl` |

---

## 3. Header / Source Dependency Map

Public headers in `include/redfish/` may only include each other and standard
library headers. Private source files in `src/` may include anything.

```
include/redfish/                        ← installed; callers include from here
├── redfish.hpp                         ← single-include convenience header
├── client.hpp                          ← connect() declaration
├── context.hpp                         ← ClientContext public interface
├── response.hpp                        ← RedfishResponse, RedfishMessage
├── errors.hpp                          ← exception hierarchy
├── task.hpp                            ← RedfishTask (public handle)
├── discovery.hpp                       ← Discovery, DiscoveryResult
├── event_listener.hpp                  ← RedfishEventListener
├── services/
│   ├── event_service.hpp
│   ├── log_service.hpp
│   ├── telemetry_service.hpp
│   └── update_service.hpp
└── redfish_c_api.h                     ← extern "C" surface for FFI

src/                                    ← private — not installed
├── client.cpp
├── context.cpp                         ← ClientContext::Impl definition
├── discovery/discovery.cpp
├── services/
│   ├── event_service.cpp
│   ├── log_service.cpp
│   ├── telemetry_service.cpp
│   └── update_service.cpp
├── events/listener.cpp
├── protocol/
│   ├── response.cpp
│   ├── task.cpp
│   └── registry.cpp
├── transport/
│   ├── http_client.cpp
│   ├── auth.cpp
│   └── tls.cpp
└── c_api/redfish_c_api.cpp
```

**Rule:** Headers in `include/redfish/` must never include from `src/`.
All implementation detail stays in `src/`.

---

## 4. SDK Entry Point — connect()

### Header: `include/redfish/client.hpp`
### Namespace: `redfish`

### Signatures

```cpp
// Sync — blocks until connected or throws
ClientContext connect(
    std::string_view  host,
    uint16_t          port,
    Credentials       credentials,
    AuthMode          auth_mode,
    ConnectionConfig  config = {}
);

// Async — coroutine, must be co_await'd
boost::asio::awaitable<ClientContext> connect_async(
    std::string_view  host,
    uint16_t          port,
    Credentials       credentials,
    AuthMode          auth_mode,
    ConnectionConfig  config = {}
);
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `host` | `std::string_view` | Hostname or IP address |
| `port` | `uint16_t` | Port (443 for BMC, 8000 for simulator) |
| `credentials` | `Credentials` | Username + password (see §19) |
| `auth_mode` | `AuthMode` | `AuthMode::Session` or `AuthMode::Stateless` |
| `config` | `ConnectionConfig` | Optional overrides; `{}` applies all defaults |

### AuthMode

```cpp
enum class AuthMode { Session, Stateless };
```

### Failure (throws)

| Failure | Exception |
|---|---|
| Host unreachable | `RedfishConnectionError` |
| TLS certificate rejected | `RedfishTLSError` |
| 401/403 | `RedfishAuthError` |
| Endpoint not Redfish-compliant | `RedfishProtocolError` |
| Invalid parameters | `std::invalid_argument` |

---

## 5. ClientContext

### Header: `include/redfish/context.hpp`
### Namespace: `redfish`

### Public Interface

```cpp
class ClientContext {
public:
    // Move-only
    ClientContext(ClientContext&&) noexcept;
    ClientContext& operator=(ClientContext&&) noexcept;
    ClientContext(const ClientContext&)            = delete;
    ClientContext& operator=(const ClientContext&) = delete;

    ~ClientContext();   // RAII — closes session, releases transport

    // State
    bool             is_connected() const;
    std::string_view base_url()     const;

    // Service handles — returned by value, thin proxy objects
    EventServiceHandle     event_service();
    LogServiceHandle       log_service();
    TelemetryServiceHandle telemetry_service();
    UpdateServiceHandle    update_service();
    Discovery              discovery();

    // Direct / raw access — sync
    RedfishResponse get   (std::string_view uri);
    RedfishResponse post  (std::string_view uri, nlohmann::json body);
    RedfishResponse patch (std::string_view uri, nlohmann::json body);
    RedfishResponse del   (std::string_view uri);

    // Direct / raw access — async
    boost::asio::awaitable<RedfishResponse> get_async   (std::string_view uri);
    boost::asio::awaitable<RedfishResponse> post_async  (std::string_view uri, nlohmann::json body);
    boost::asio::awaitable<RedfishResponse> patch_async (std::string_view uri, nlohmann::json body);
    boost::asio::awaitable<RedfishResponse> del_async   (std::string_view uri);

    // v0.2 — re-authenticate without creating a new context
    void refresh_auth();

    // Lifecycle (RAII preferred — destructor handles this automatically)
    void close();
    boost::asio::awaitable<void> close_async();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
```

### Impl (Private — `src/context.cpp`)

All data members hidden in `Impl`. Never visible to callers.

| Member | Type | Description |
|---|---|---|
| `http_client` | `HttpClient` | Internal HTTP client instance |
| `auth_state` | `AuthState` | Auth mode + token or credentials |
| `capabilities` | `EndpointCapabilities` | Negotiated at connect time |
| `schema_cache` | `std::unordered_map<std::string, nlohmann::json>` | Schemas fetched from BMC |
| `discovery_map` | `std::unordered_map<std::string, std::string>` | Service name → URI |
| `config` | `ConnectionConfig` | Effective config for this connection |
| `io_context` | `boost::asio::io_context` | Drives async operations for sync wrappers |

### Service Handle Pattern

Service handles are thin proxy objects. They are constructed with a reference
to `Impl` and own no state.

```cpp
EventServiceHandle ClientContext::event_service() {
    return EventServiceHandle{*impl_};
}
```

Handles are cheap to construct. Callers can request them on every call — no
need to cache the handle.

---

## 6. ConnectionConfig

### Header: `include/redfish/context.hpp`
### Namespace: `redfish`

```cpp
struct ConnectionConfig {
    bool        verify_tls             = true;
    std::string tls_ca_cert            = "";        // empty = use system CA store
    float       connect_timeout_sec    = 10.0f;
    float       request_timeout_sec    = 30.0f;
    float       task_poll_interval_sec = 5.0f;
    float       task_timeout_sec       = 300.0f;
    std::string base_path_override     = "";        // empty = /redfish/v1
    bool        allow_session_fallback = false;

    // v0.2 — retry (FR1.8, FR1.9)
    int              retry_on_connection_failure = 0;   // 0 = no retry
    std::vector<int> retry_status_codes          = {};  // e.g. {503, 429}
    double           retry_delay_sec             = 2.0; // seconds between attempts
};
```

All fields have defaults. Pass `{}` to accept all defaults.

### Retry behaviour (v0.2)

| Field | Meaning |
|---|---|
| `retry_on_connection_failure` | Number of extra attempts after a transport error |
| `retry_status_codes` | HTTP status codes that trigger a retry (e.g. `503`, `429`) |
| `retry_delay_sec` | Fixed delay between attempts |

TLS errors (`RedfishTLSError`) are never retried. Retry logic lives in `DefaultHttpClient::request()`.

---

## 7. Discovery

### Header: `include/redfish/discovery.hpp`
### Namespace: `redfish`
### Accessed via: `ctx.discovery()`

### Public Interface

```cpp
class Discovery {
public:
    // Sync
    DiscoveryResult full();
    DiscoveryResult partial(std::string_view service_name);
    DiscoveryResult root();

    // Async
    boost::asio::awaitable<DiscoveryResult> full_async();
    boost::asio::awaitable<DiscoveryResult> partial_async(std::string_view service_name);
    boost::asio::awaitable<DiscoveryResult> root_async();
};
```

### Discovery Modes

| Mode | Method | Behaviour |
|---|---|---|
| **Root** | `root()` | GET `/redfish/v1` only — enumerate top-level links, no traversal |
| **Partial** | `partial(name)` | GET ServiceRoot, then GET the named service only |
| **Full** | `full()` | GET ServiceRoot, then GET all top-level service links one level deep |

### DiscoveryResult

```cpp
struct DiscoveryResult {
    std::unordered_map<std::string, std::string> services;      // name → URI
    std::vector<std::string>                     capabilities;  // service names found
    nlohmann::json                               raw;           // raw ServiceRoot JSON

    bool        has_service(std::string_view name) const;
    std::string service_uri(std::string_view name) const;   // empty string if not found
};
```

### Side Effect

After any discovery call, `Impl::discovery_map` is updated. Service handles
use this map to resolve their target URI without re-fetching ServiceRoot.

---

## 8. RedfishResponse

### Header: `include/redfish/response.hpp`
### Namespace: `redfish`

```cpp
struct RedfishMessage {
    std::string                message_id;
    std::string                message;
    std::string                severity;
    std::optional<std::string> resolution;
    std::vector<std::string>   message_args;
};

struct RedfishResponse {
    int                                          status_code;
    bool                                         success;       // true if 2xx
    std::unordered_map<std::string, std::string> headers;
    nlohmann::json                               body;          // null if no body
    std::vector<RedfishMessage>                  extended_info;
    std::optional<RedfishTask>                   task;          // populated on 202
    std::string                                  raw;
};
```

`RedfishResponse` is a value type — copyable and movable. `RedfishTask` is
forward-declared in `response.hpp`, defined in `task.hpp`.

---

## 9. RedfishTask and TaskManager

### Header: `include/redfish/task.hpp`
### Namespace: `redfish`

### RedfishTask (Public)

```cpp
class RedfishTask {
public:
    std::string                 task_uri;
    std::string                 task_id;
    TaskState                   state;
    std::optional<int>          percent_complete;
    std::vector<RedfishMessage> messages;

    // Sync — blocks until terminal state or throws on timeout
    RedfishResponse wait(
        std::optional<float> poll_interval_sec = std::nullopt,
        std::optional<float> timeout_sec       = std::nullopt
    );

    // Async
    boost::asio::awaitable<RedfishResponse> wait_async(
        std::optional<float> poll_interval_sec = std::nullopt,
        std::optional<float> timeout_sec       = std::nullopt
    );

    // Async — callback on each state change
    boost::asio::awaitable<void> monitor_async(
        std::function<void(TaskState, const RedfishTask&)> on_state_change,
        std::optional<float> timeout_sec = std::nullopt
    );

    // Cancel the task (if BMC supports it)
    RedfishResponse                         cancel();
    boost::asio::awaitable<RedfishResponse> cancel_async();
};
```

### TaskState Enum

```cpp
enum class TaskState {
    New, Starting, Running, Suspended, Interrupted,
    Pending, Stopping, Completed, Killed, Exception,
    Service, Cancelling, Cancelled
};
```

Terminal states (polling stops): `Completed`, `Killed`, `Exception`, `Cancelled`.

### TaskManager (Internal — `src/protocol/task.cpp`)

Not in any public header. Used by `RedfishTask::wait()` / `wait_async()`.

Behaviour:
1. Poll task URI at `poll_interval_sec` intervals
2. Parse `TaskState` and `PercentComplete` from each response
3. Update `RedfishTask` state fields on each poll
4. Invoke `on_state_change` callback if registered
5. Stop at terminal state or `timeout_sec` expiry
6. On timeout → throw `RedfishTaskTimeoutError`
7. On terminal failure state → throw `RedfishTaskFailedError` with final response detail

---

## 10. MessageRegistry

### Internal — `src/protocol/registry.cpp`
### Not in any public header.

Used internally by `EventServiceHandle`, `LogServiceHandle`, and
`RedfishEventListener` for `MessageId` resolution.

### Internal Interface

```cpp
class MessageRegistry {
public:
    explicit MessageRegistry(HttpClient& http_client);

    std::optional<RedfishMessage>                    resolve(std::string_view message_id);
    boost::asio::awaitable<std::optional<RedfishMessage>> resolve_async(std::string_view message_id);

    bool                          fetch(std::string_view registry_prefix);
    boost::asio::awaitable<bool>  fetch_async(std::string_view registry_prefix);
};
```

### MessageId Format

```
RegistryPrefix.MajorVersion.MinorVersion.MessageKey
Example: Base.1.8.Success
```

### Resolution Flow

Parse prefix → check cache → on miss: GET `/redfish/v1/Registries/{prefix}/{prefix}.json`
→ cache → look up message key → return `RedfishMessage`. Cache persists for the
lifetime of the `ClientContext`.

---

## 11. EventServiceHandle

### Header: `include/redfish/services/event_service.hpp`
### Namespace: `redfish`
### Accessed via: `ctx.event_service()`

### URI Resolution

Priority order:
1. `Impl::discovery_map["EventService"]` (if discovery was run)
2. `{base_url}/redfish/v1/EventService` (default)

### Public Interface

```cpp
class EventServiceHandle {
public:
    // Query service info
    RedfishResponse get_service_info();
    boost::asio::awaitable<RedfishResponse> get_service_info_async();

    // Subscription management
    RedfishResponse subscribe(
        std::string_view         destination,
        std::vector<std::string> event_types        = {},
        std::vector<std::string> registry_prefixes  = {},
        std::vector<std::string> message_ids        = {},
        std::vector<std::string> resource_types     = {},  // FR5.1 v0.3
        std::string              event_format_type  = "",   // FR5.1 v0.3
        std::string              context            = "",
        std::string              protocol           = "Redfish",
        std::string              subscription_type  = "RedfishEvent"
    );
    boost::asio::awaitable<RedfishResponse> subscribe_async(/* same params */);

    RedfishResponse list_subscriptions();
    boost::asio::awaitable<RedfishResponse> list_subscriptions_async();

    RedfishResponse get_subscription(std::string_view subscription_uri);
    boost::asio::awaitable<RedfishResponse> get_subscription_async(std::string_view subscription_uri);

    RedfishResponse delete_subscription(std::string_view subscription_uri);
    boost::asio::awaitable<RedfishResponse> delete_subscription_async(std::string_view subscription_uri);

    // SSE streaming — calls on_event for each received event; runs until cancelled
    boost::asio::awaitable<void> subscribe_sse(
        std::function<void(const RedfishEvent&)> on_event,
        nlohmann::json                           filters = {}
    );

    // Submit test event (simulator / test use)
    RedfishResponse submit_test_event(const nlohmann::json& event_data);
    boost::asio::awaitable<RedfishResponse> submit_test_event_async(const nlohmann::json& event_data);
};
```

### RedfishEvent

```cpp
struct RedfishEvent {
    std::string                event_id;
    std::string                event_type;
    std::string                event_timestamp;
    std::string                message_id;
    std::string                message;
    std::string                severity;
    std::optional<std::string> origin_of_condition;
    nlohmann::json             raw;
};
```

### SSE vs Push

- `subscribe_sse` streams events over a persistent HTTP connection (simulator/test).
- Push delivery uses `RedfishEventListener` (production BMC environments).

---

## 12. LogServiceHandle

### Header: `include/redfish/services/log_service.hpp`
### Namespace: `redfish`
### Accessed via: `ctx.log_service()`

### LogQuery (FR6.2 / FR6.7 / FR6.8 — v0.4)

A value type that encapsulates all OData query parameters for log entry
retrieval.  The SDK builds the query string internally in the order required
by OpenBMC implementations: **`$skip` → `$top` → `$filter`**.

```cpp
// Typed OData query parameters for log entry retrieval.
// Query string is built in BMC-required order: $skip → $top → $filter
struct LogQuery {
    std::optional<int>         top;           // $top — max entries returned
    std::optional<int>         skip;          // $skip — first N entries to skip
    std::optional<std::string> severity;      // $filter=Severity eq '<value>'
    std::optional<std::string> message_id;    // $filter=MessageId eq '<value>'
    std::optional<std::string> odata_filter;  // raw $filter (overrides severity/message_id)
};
```

### Public Interface

```cpp
class LogServiceHandle {
public:
    RedfishResponse list_services();

    // Fetch one page of entries.
    // Query string is built in required OData order: $skip → $top → $filter
    RedfishResponse list_entries(
        const std::string& log_uri,
        const LogQuery&    query = {}
    );

    // Follow Members@odata.nextLink until exhausted or on_page returns false.
    // on_page receives one full RedfishResponse per page.
    void iter_entries(
        const std::string&                             log_uri,
        std::function<bool(const RedfishResponse&)>    on_page,
        const LogQuery&                                query = {}
    );

    RedfishResponse get_entry(const std::string& entry_uri);

    RedfishResponse clear_log(const std::string& log_uri);
};
```

### v0.2 — SEL Parsing

The SDK now ships a standalone helper for decoding OpenBMC binary SEL entries
(FR8.2). It lives in `redfish_types.hpp` and has no network dependency.

```cpp
struct ParsedSelRecord {
    std::string record_type;  // "PxeBoot" | "HostOsModeChange" | "HostOsHandOff" | "Unknown"
    uint32_t    timestamp = 0;
    std::string raw_hex;
};

// Decode a raw SEL hex string (space-separated or plain).
// Strips "5A 52 52 49..." OpenBMC prefix if present.
// Returns ParsedSelRecord{record_type="Unknown"} on unrecognised payload.
// Throws std::invalid_argument on malformed hex or insufficient bytes.
ParsedSelRecord parse_sel_entry(const std::string& raw_hex);
```

#### Byte-level decode rules

| Condition | `record_type` |
|---|---|
| byte[0] == 0xCA | `"PxeBoot"` |
| byte[0] == 0xD9 && byte[13] == 0x01 | `"HostOsModeChange"` |
| byte[0] == 0xD9 && byte[13] == 0x02 | `"HostOsHandOff"` |
| otherwise | `"Unknown"` |

Timestamp = bytes[3..6] decoded as little-endian `uint32_t` (Unix epoch).

---

## 13. TelemetryServiceHandle

### Header: `include/redfish/services/telemetry_service.hpp`
### Namespace: `redfish`
### Accessed via: `ctx.telemetry_service()`

### Public Interface

```cpp
class TelemetryServiceHandle {
public:
    RedfishResponse get_service_info();
    boost::asio::awaitable<RedfishResponse> get_service_info_async();

    RedfishResponse list_metric_report_definitions();
    boost::asio::awaitable<RedfishResponse> list_metric_report_definitions_async();

    RedfishResponse get_metric_report_definition(std::string_view definition_uri);
    boost::asio::awaitable<RedfishResponse> get_metric_report_definition_async(std::string_view definition_uri);

    RedfishResponse list_metric_reports();
    boost::asio::awaitable<RedfishResponse> list_metric_reports_async();

    RedfishResponse get_metric_report(std::string_view report_uri);
    boost::asio::awaitable<RedfishResponse> get_metric_report_async(std::string_view report_uri);

    // Streaming — calls on_report for each report received; runs until cancelled
    boost::asio::awaitable<void> stream_metric_reports(
        std::function<void(const MetricReport&)>  on_report,
        std::optional<std::string_view>           definition_uri = std::nullopt
    );
};
```

### MetricReport and MetricValue

```cpp
struct MetricValue {
    std::string                metric_id;
    std::string                metric_value;    // raw string; caller parses if numeric
    std::string                timestamp;
    std::optional<std::string> metric_property;
};

struct MetricReport {
    std::string              report_id;
    std::string              report_uri;
    std::string              timestamp;
    std::vector<MetricValue> metric_values;
    nlohmann::json           raw;
};
```

---

## 14. UpdateServiceHandle

### Header: `include/redfish/services/update_service.hpp`
### Namespace: `redfish`
### Accessed via: `ctx.update_service()`

### Public Interface

```cpp
class UpdateServiceHandle {
public:
    RedfishResponse get_service_info();
    boost::asio::awaitable<RedfishResponse> get_service_info_async();

    RedfishResponse list_firmware_inventory();
    boost::asio::awaitable<RedfishResponse> list_firmware_inventory_async();

    RedfishResponse get_firmware_component(std::string_view component_uri);
    boost::asio::awaitable<RedfishResponse> get_firmware_component_async(std::string_view component_uri);

    RedfishResponse list_software_inventory();
    boost::asio::awaitable<RedfishResponse> list_software_inventory_async();

    RedfishResponse get_software_component(std::string_view component_uri);
    boost::asio::awaitable<RedfishResponse> get_software_component_async(std::string_view component_uri);

    // Returns RedfishResponse; response.task is populated if BMC returns 202
    RedfishResponse simple_update(
        std::string_view           image_uri,
        std::vector<std::string>   targets           = {},
        std::optional<std::string> transfer_protocol = std::nullopt,
        std::optional<std::string> apply_time        = std::nullopt
    );
    boost::asio::awaitable<RedfishResponse> simple_update_async(/* same params */);

    // v0.2 — multipart HTTP push (FR7.5)
    // Reads firmware_path from disk, POSTs to MultipartHttpPushUri (or HttpPushUri fallback)
    // update_params is merged into the UpdateParameters JSON part
    RedfishResponse push_firmware(
        const std::string&    firmware_path,
        const nlohmann::json& update_params = {}
    );
};

### push_firmware flow (v0.2)

```
1. GET UpdateService resource → extract MultipartHttpPushUri (preferred) or HttpPushUri
2. If neither present → throw RedfishProtocolError
3. Read firmware file into memory buffer
4. POST multipart/form-data to push URI:
     Part 1 (name="UpdateParameters", Content-Type: application/json): update_params JSON
     Part 2 (name="UpdateFile", Content-Type: application/octet-stream): firmware bytes
5. Return RedfishResponse; task populated on 202
```
```

---

## 15. RedfishEventListener

### Header: `include/redfish_sdk/event_listener.hpp`
### Source: `src/events/listener.cpp`
### Namespace: `redfish`

### Public Interface

```cpp
class RedfishEventListener {
public:
    explicit RedfishEventListener(
        uint16_t         port,
        std::string_view host            = "0.0.0.0",
        std::string_view expected_context = "",   // FR5.3 context validation
        uint32_t         buffer_size     = 200    // FR5.3 ring buffer capacity
    );

    ~RedfishEventListener();    // RAII — calls stop() if running

    // Move-only
    RedfishEventListener(RedfishEventListener&&) noexcept;
    RedfishEventListener& operator=(RedfishEventListener&&) noexcept;
    RedfishEventListener(const RedfishEventListener&)            = delete;
    RedfishEventListener& operator=(const RedfishEventListener&) = delete;

    // Wire to context for MessageRegistry decoding (optional)
    void use_context(ClientContext& ctx);

    // Register callbacks — all events
    void on_event(std::function<void(const RedfishEvent&)> callback);

    // Register callbacks — filtered by EventType string
    void on_event_type(
        std::string_view                          event_type,
        std::function<void(const RedfishEvent&)>  callback
    );

    // Register callbacks — filtered by MessageId registry prefix
    void on_registry(
        std::string_view                          registry_prefix,
        std::function<void(const RedfishEvent&)>  callback
    );

    // Lifecycle
    void start();   // non-blocking — starts internal POSIX-socket thread
    void stop();    // graceful shutdown — blocks until thread exits

    bool        is_running()  const;
    std::string listen_url()  const;    // e.g. "http://0.0.0.0:9090/events"

    // FR5.3 — buffered event retrieval
    std::vector<RedfishEvent> get_buffered_events() const;

    // FR5.3 — per-source-IP event counts
    std::map<std::string, uint32_t> get_ip_stats() const;
};
```

### Internal Threading

`RedfishEventListener` owns a raw POSIX TCP socket and two `std::thread`s:

1. **Supervisor thread** — loops on `accept()` until a stop flag is set.
   Uses a self-pipe to wake the `select()`/`poll()` call so `stop()` returns
   promptly without waiting for the next `accept()` timeout.
2. **Per-connection thread** (short-lived) — spawned for each accepted connection;
   reads the HTTP request, parses the JSON body, dispatches callbacks, writes
   `204 No Content`, then exits.

The destructor sets the stop flag and joins the supervisor thread before returning.

### Context Validation (FR5.3)

If `expected_context` is non-empty, the `Context` field of each incoming event
JSON is compared.  On mismatch: respond `204 No Content` without invoking any
callbacks and without appending to the ring buffer.

### Latency Logging (FR5.3)

After parsing `EventTimestamp` (ISO 8601), the supervisor thread computes the
wall-clock delta from the reception time and logs it at `DEBUG` level.

### Per-IP Counter (FR5.3)

A `std::map<std::string, uint32_t>` protected by a `std::mutex` tracks
cumulative event counts per source IP.  `get_ip_stats()` returns a copy.

### Ring Buffer (FR5.3)

A `std::deque<RedfishEvent>` capped at `buffer_size` stores the most recent
events.  `get_buffered_events()` returns a copy.  A `GET` on the listen path
serialises the buffer to JSON and responds `200 OK`.

### SEL note

Events with `MessageId` prefix `"OpenBMC"` and `Message` starting with
`"Raw data: "` are recognised as flat-SEL events.  The listener passes them
to callbacks as normal `RedfishEvent` objects; callers may further call
`parse_sel_entry(event.message)` to decode the SEL bytes.

---

## 16. Transport Layer — HttpClient (v0.2)

### Header: `include/redfish_sdk/transport/http_client.hpp`
### Source: `src/transport/http_client.cpp`

v0.2 introduces a three-tier abstraction (NFR8.2 — injectable/mockable transport):

```
IHttpClient          ← abstract base (pure virtual)
  ├── DefaultHttpClient   ← libcurl production impl, retry loop, multipart
  └── MockHttpClient      ← test double: canned (method, path) → RawHttpResponse

using HttpClient = DefaultHttpClient;   // legacy alias — keeps v0.1 code compiling
```

### IHttpClient (abstract base)

```cpp
class IHttpClient {
public:
    virtual ~IHttpClient() = default;

    virtual RawHttpResponse request(
        const std::string&                        method,
        const std::string&                        path,
        const std::map<std::string, std::string>& headers = {},
        const std::optional<std::string>&         body    = std::nullopt
    ) = 0;

    // Multipart POST — fields are plain text, files are binary blobs (FR7.5)
    virtual RawHttpResponse request_multipart(
        const std::string&                                    path,
        const std::map<std::string, std::string>&             headers,
        const std::map<std::string, std::string>&             fields,
        const std::map<std::string, std::vector<uint8_t>>&   files = {}
    ) = 0;

    virtual const std::string& base_url() const = 0;
};
```

### DefaultHttpClient

```cpp
class DefaultHttpClient : public IHttpClient {
public:
    DefaultHttpClient(
        const std::string&      base_url,
        const TLSConfig&        tls,
        const TimeoutConfig&    timeouts,
        const ConnectionConfig& config = {}   // supplies retry fields
    );
    // request() and request_multipart() implemented via libcurl + curl_mime
};
```

#### Retry loop (FR1.8, FR1.9)

```
for attempt in 0 .. retry_count:
    response = execute_once(method, path, ...)
    if response.status_code in retry_status_codes:
        sleep(retry_delay_sec); continue
    return response
  except RedfishTLSError:
    raise immediately   # TLS errors never retried
  except RedfishConnectionError:
    sleep(retry_delay_sec); continue
raise last_exception
```

#### HTTPS-always design

The SDK always uses `https://`. Setting `verify_tls=false` only disables cert
verification (`CURLOPT_SSL_VERIFYPEER=0`); it does **not** downgrade to HTTP.
A non-fatal HTTP GET probe to `/redfish/v1` is performed before the main
HTTPS connection for initial service discovery (e.g. simulators that expose
plain HTTP on that path).

### MockHttpClient (test double)

```cpp
class MockHttpClient : public IHttpClient {
public:
    explicit MockHttpClient(const std::string& base_url = "mock://localhost");

    // Register a canned response keyed on (METHOD, path)
    void register_response(
        const std::string& method,
        const std::string& path,
        RawHttpResponse    response
    );

    // Inspect recorded calls for assertions
    struct RecordedCall { std::string method; std::string path; };
    const std::vector<RecordedCall>& recorded_calls() const;
};
```

`request()` and `request_multipart()` look up `(METHOD, path)` in the
registered map and return the canned response, or a synthetic 404 if not found.
All calls are appended to `recorded_calls()` for verification in tests.

### Logging

All transport layer operations emit structured log messages via the internal
logger (`src/internal/logger.hpp`). Log level is controlled by the
`REDFISH_SDK_LOG_LEVEL` environment variable:

| Value | Meaning |
|---|---|
| `DEBUG` | All HTTP attempts, retry loops, auth steps |
| `INFO` | Connection established, auth mode |
| `WARNING` | Connection attempt failed (retry pending) |
| `ERROR` | All attempts exhausted |
| `OFF` (default) | No output |

Output goes to `std::clog`.

---

## 17. Transport Layer — AuthManager

### Source: `src/transport/auth.cpp`
### Not in any public header.

### Internal Interface

```cpp
class AuthManager {
public:
    AuthManager(HttpClient& http_client, Credentials credentials, AuthMode mode);

    AuthState                         authenticate();
    boost::asio::awaitable<AuthState> authenticate_async();

    void attach_auth(std::unordered_map<std::string, std::string>& headers) const;

    void                         logout();
    boost::asio::awaitable<void> logout_async();
};
```

### AuthState (Internal)

```cpp
struct AuthState {
    AuthMode                   mode;
    std::optional<std::string> session_token;
    std::optional<std::string> session_uri;
    Credentials                credentials;
};
```

### Session Auth Flow

```
authenticate() — Session mode:
    POST {base_url}/redfish/v1/SessionService/Sessions
    body: { "UserName": ..., "Password": ... }
    → 201 Created
    → Extract X-Auth-Token header → session_token
    → Extract Location header → session_uri
    → Store in AuthState
```

### Stateless Auth Flow

```
authenticate() — Stateless mode:
    GET {base_url}/redfish/v1
    with Basic Auth header
    → 200 OK (validates endpoint + credentials)
    → Store credentials in AuthState for per-request attachment
```

### Auth Attachment

```
attach_auth() — Session mode:
    headers["X-Auth-Token"] = auth_state.session_token.value()

attach_auth() — Stateless mode:
    encode credentials as HTTP Basic Auth
    headers["Authorization"] = "Basic {encoded}"
```

---

## 18. Transport Layer — TLS

### Source: `src/transport/tls.cpp`
### Not in any public header.

### Internal Interface

```cpp
TLSConfig build_tls_config(const ConnectionConfig& config);

struct TLSConfig {
    bool        verify       = true;
    std::string ca_cert_path = "";   // empty = system CA store
    std::string client_cert  = "";   // empty = no mTLS
    std::string client_key   = "";
};
```

### Mapping from ConnectionConfig

| `ConnectionConfig` field | `TLSConfig` result |
|---|---|
| `verify_tls=true`, no CA cert | `verify=true`, `ca_cert_path=""` (system store) |
| `verify_tls=true`, `tls_ca_cert` set | `verify=true`, `ca_cert_path=tls_ca_cert` |
| `verify_tls=false` | `verify=false` (dev/test only) |

---

## 19. Internal Data Contracts

Defined in internal headers under `src/`. Not installed.

### Credentials

```cpp
struct Credentials {
    std::string username;
    std::string password;
};
```

### AuthMode

```cpp
enum class AuthMode { Session, Stateless };
```

### ParsedSelRecord (v0.2)

See §12 (LogServiceHandle) for full decode specification.

```cpp
struct ParsedSelRecord {
    std::string record_type;  // "PxeBoot" | "HostOsModeChange" | "HostOsHandOff" | "Unknown"
    uint32_t    timestamp = 0;
    std::string raw_hex;
};

ParsedSelRecord parse_sel_entry(const std::string& raw_hex);
```

Defined in `include/redfish_sdk/models/redfish_types.hpp`.

### EndpointCapabilities

```cpp
struct EndpointCapabilities {
    std::string              redfish_version;
    std::string              odata_version;
    bool                     short_form;
    std::string              base_path;
    std::vector<std::string> available_services;
};
```

### TimeoutConfig

```cpp
struct TimeoutConfig {
    float connect_sec      = 10.0f;
    float request_sec      = 30.0f;
    float task_poll_sec    = 5.0f;
    float task_timeout_sec = 300.0f;
};
```

---

## 20. Error Design

### Philosophy

Mirrors Python exactly. Transport/auth failures throw. HTTP-level responses
(4xx/5xx) return `RedfishResponse` with `success=false`. 404 is never an
exception.

### Exception Hierarchy

Defined in `include/redfish/errors.hpp`.

```cpp
class RedfishSDKError     : public std::exception { ... };  // base

class RedfishConnectionError : public RedfishSDKError { ... };
class RedfishTLSError        : public RedfishSDKError { ... };
class RedfishAuthError       : public RedfishSDKError { ... };
class RedfishProtocolError   : public RedfishSDKError { ... };

class RedfishHTTPError       : public RedfishSDKError {
public:
    int             status_code;
    RedfishResponse response;
};

class RedfishTaskTimeoutError : public RedfishSDKError {
public:
    RedfishTask task;
};

class RedfishTaskFailedError  : public RedfishSDKError {
public:
    RedfishTask task;
};
```

### What Throws vs What Returns

| Situation | SDK Behaviour |
|---|---|
| Network failure | Throws `RedfishConnectionError` |
| TLS cert rejected | Throws `RedfishTLSError` |
| 401 / 403 | Throws `RedfishAuthError` |
| 404 | Returns `RedfishResponse{success=false, status_code=404}` |
| Other 4xx / 5xx | Returns `RedfishResponse{success=false}` |
| 2xx | Returns `RedfishResponse{success=true}` |
| 202 | Returns `RedfishResponse` with `task` populated |
| Task timeout | Throws `RedfishTaskTimeoutError` |
| Task failed state | Throws `RedfishTaskFailedError` |

---

## 21. Async and Sync Model

### Pattern

All logic is written once as a C++20 coroutine (`co_await`). Sync variants
drive the coroutine to completion using `boost::asio::co_spawn` with a
`use_future` token on the context's `io_context`.

```cpp
// Async — all logic lives here
boost::asio::awaitable<RedfishResponse>
ClientContext::get_async(std::string_view uri) {
    // ... full logic using co_await
    co_return response;
}

// Sync — drives the async path, no duplicate logic
RedfishResponse ClientContext::get(std::string_view uri) {
    return boost::asio::co_spawn(
        impl_->io_context,
        get_async(uri),
        boost::asio::use_future
    ).get();
}
```

### Naming Convention

Same as Python — async suffix on the coroutine variant, plain name for sync:

| Async variant | Sync variant |
|---|---|
| `connect_async(...)` | `connect(...)` |
| `get_async(uri)` | `get(uri)` |
| `subscribe_async(...)` | `subscribe(...)` |
| `full_async()` | `full()` |
| `wait_async(...)` | `wait(...)` |

---

## 22. extern "C" Surface

### Header: `include/redfish/redfish_c_api.h`
### Source: `src/c_api/redfish_c_api.cpp`

### Purpose

A thin C-compatible wrapper over the C++ API. Contains no business logic —
pure translation. Enables Rust FFI in Phase 3 without any changes to the
C++ SDK.

### Design Rules

- All SDK handles are opaque `void*` pointers
- All strings are `const char*` (null-terminated)
- JSON bodies are serialized as `const char*` (JSON string)
- All functions return `int` error code — `0` is success
- Complex return values are written through output pointer parameters
- Memory ownership is documented per function

### Handle Types

```c
typedef void* redfish_ctx_t;
typedef void* redfish_response_t;
typedef void* redfish_task_t;
typedef void* redfish_listener_t;
```

### Error Codes

```c
#define REDFISH_OK                0
#define REDFISH_ERR_CONNECTION    1
#define REDFISH_ERR_TLS           2
#define REDFISH_ERR_AUTH          3
#define REDFISH_ERR_PROTOCOL      4
#define REDFISH_ERR_HTTP          5
#define REDFISH_ERR_TASK_TIMEOUT  6
#define REDFISH_ERR_TASK_FAILED   7
#define REDFISH_ERR_INVALID_ARG   8
```

### Core Functions

```c
// Connect — caller owns ctx; free with redfish_destroy_context
int redfish_connect(
    const char*    host,
    uint16_t       port,
    const char*    username,
    const char*    password,
    int            auth_mode,       // 0=Session, 1=Stateless
    redfish_ctx_t* out_ctx
);

// Destroy context — closes session, frees all resources
void redfish_destroy_context(redfish_ctx_t ctx);

// Raw HTTP — caller owns response; free with redfish_destroy_response
int redfish_get  (redfish_ctx_t ctx, const char* uri, redfish_response_t* out_response);
int redfish_post (redfish_ctx_t ctx, const char* uri, const char* body_json, redfish_response_t* out_response);
int redfish_patch(redfish_ctx_t ctx, const char* uri, const char* body_json, redfish_response_t* out_response);
int redfish_del  (redfish_ctx_t ctx, const char* uri, redfish_response_t* out_response);

// Response accessors — pointers valid until redfish_destroy_response
int         redfish_response_status_code(redfish_response_t r);
int         redfish_response_success    (redfish_response_t r);  // 1=true, 0=false
const char* redfish_response_body_json  (redfish_response_t r);  // do not free
const char* redfish_response_raw        (redfish_response_t r);  // do not free

void redfish_destroy_response(redfish_response_t r);

// Task — caller owns task handle; free with redfish_destroy_task
int            redfish_response_has_task   (redfish_response_t r);
redfish_task_t redfish_response_get_task   (redfish_response_t r);
int            redfish_task_wait           (redfish_task_t task, float timeout_sec, redfish_response_t* out_response);
void           redfish_destroy_task        (redfish_task_t task);

// Event Listener — caller owns listener; free with redfish_listener_destroy
int  redfish_listener_create (uint16_t port, const char* host, redfish_listener_t* out_listener);
int  redfish_listener_start  (redfish_listener_t listener);
void redfish_listener_stop   (redfish_listener_t listener);
void redfish_listener_destroy(redfish_listener_t listener);

// Register event callback
// Callback signature: void callback(const char* event_json, void* user_data)
int redfish_listener_on_event(
    redfish_listener_t listener,
    void (*callback)(const char* event_json, void* user_data),
    void* user_data
);

// Last error message — valid until next call on this ctx
const char* redfish_last_error(redfish_ctx_t ctx);
```

---

## 23. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — C++ design |
| 0.2 | 2026-03-06 | Hari | Retry/refresh (FR1.8–1.10); IHttpClient/MockHttpClient (NFR8.2); `push_firmware()` multipart (FR7.5); SEL parsing (FR8.2); env-controlled logging (NFR5.1); always-HTTPS transport |
| 0.3 | 2026-03-07 | Copilot | §11 subscribe() gains `resource_types` + `event_format_type` (FR5.1); §15 RedfishEventListener redesigned — POSIX socket, context validation, latency logging, per-IP counter, ring buffer, buffered GET (FR5.3) |
| 0.4 | 2026-03-05 | Copilot | §12 `LogQuery` struct added; `list_entries()` updated to accept `LogQuery`; `iter_entries()` added for nextLink auto-pagination (FR6.8); OData ordering enforcement documented (FR6.7) |
