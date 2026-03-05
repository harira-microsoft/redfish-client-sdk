# Redfish Client SDK — Python Design

**Document ID:** RSDK-DESIGN-001  
**Version:** 0.2  
**Status:** Locked  
**Date:** March 5, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Architecture Ref:** RSDK-ARCH-001, RSDK-ARCH-002  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Design Principles](#2-design-principles)
3. [Module Dependency Map](#3-module-dependency-map)
4. [SDK Entry Point — connect()](#4-sdk-entry-point--connect)
5. [ClientContext](#5-clientcontext)
6. [ConnectionConfig](#6-connectionconfig)
7. [Discovery](#7-discovery)
8. [RedfishResponse](#8-redfishresponse)
9. [RedfishTask and TaskManager](#9-redfishask-and-taskmanager)
10. [MessageRegistry](#10-messageregistry)
11. [EventService Handle](#11-eventservice-handle)
12. [LogService Handle](#12-logservice-handle)
13. [TelemetryService Handle](#13-telemetryservice-handle)
14. [UpdateService Handle](#14-updateservice-handle)
15. [RedfishEventListener](#15-redfisheventlistener)
16. [Transport Layer — HttpClient](#16-transport-layer--httpclient)
17. [Transport Layer — AuthManager](#17-transport-layer--authmanager)
18. [Transport Layer — TLS](#18-transport-layer--tls)
19. [Internal Data Contracts](#19-internal-data-contracts)
20. [Error Design](#20-error-design)
21. [Async and Sync Bridge](#21-async-and-sync-bridge)
22. [Sequence Diagrams](#22-sequence-diagrams)
23. [Change History](#23-change-history)

---

## 1. Purpose

This document defines the **detailed design** of the Python SDK. It bridges
the architecture (RSDK-ARCH-002) and the implementation — specifying every
module's public interface, its internal contracts, data flows, and
interaction patterns.

A developer picking up this document should be able to implement any
module without making design decisions. All design decisions are made here.

**Design is not code.** This document specifies interfaces, signatures,
data shapes, and flows — not implementation logic.

---

## 2. Design Principles

| Principle | Expression in This Design |
|---|---|
| One function to start | `connect()` / `connect_async()` are the only SDK entry points |
| Opaque handle | `ClientContext` internal state is private — never directly readable by callers |
| Async-first | All logic is async; sync variants call async via `asyncio.run()` |
| Uniform response | Every public method returns `RedfishResponse` |
| No caller state management | SDK holds session token, schema cache, capabilities — caller holds only the context |
| Lazy service access | Service handles are instantiated on first property access, not at connect time |
| Graceful degradation | Missing resources return empty results; unknown fields are preserved |

---

## 3. Module Dependency Map

The following shows which modules may import from which. No module shall
import from a module above it in this hierarchy.

```
redfish_sdk/
│
├── __init__.py                  ← exports: connect, connect_async, RedfishEventListener
│
├── client.py                    ← imports: context, transport, models
├── context.py                   ← imports: discovery, services, protocol, transport
│
├── discovery/
│   └── discovery.py             ← imports: protocol, transport
│
├── services/
│   ├── event_service.py         ← imports: protocol, transport
│   ├── log_service.py           ← imports: protocol, transport
│   ├── telemetry_service.py     ← imports: protocol, transport
│   └── update_service.py        ← imports: protocol, transport
│
├── events/
│   └── listener.py              ← imports: protocol, models
│
├── protocol/
│   ├── response.py              ← imports: models only
│   ├── task.py                  ← imports: transport, models
│   └── registry.py              ← imports: transport, models
│
├── transport/
│   ├── http_client.py           ← imports: models only (no SDK imports)
│   ├── auth.py                  ← imports: http_client, models
│   └── tls.py                   ← imports: models only
│
└── models/
    └── redfish_types.py         ← imports: nothing (pure data types)
```

**Rule:** `transport/` modules never import from `services/`, `protocol/`,
or `context/`. `models/` imports nothing from within the SDK.

---

## 4. SDK Entry Point — connect()

### Module: `redfish_sdk/client.py`  
### Exported via: `redfish_sdk/__init__.py`

---

### Purpose

The single callable that a client team uses to establish a connection.
Returns a `ClientContext` handle on success. Raises on failure.

---

### Public Signatures

```
connect(
    host        : str,
    port        : int,
    credentials : Credentials,
    auth_mode   : AuthMode,
    config      : ConnectionConfig | None = None
) -> ClientContext
```

```
connect_async(
    host        : str,
    port        : int,
    credentials : Credentials,
    auth_mode   : AuthMode,
    config      : ConnectionConfig | None = None
) -> Awaitable[ClientContext]
```

---

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `host` | `str` | Hostname or IP address of the Redfish endpoint |
| `port` | `int` | Port number (typically 443 for real BMC, 8000 for simulator) |
| `credentials` | `Credentials` | Username and password (see §19) |
| `auth_mode` | `AuthMode` | `AuthMode.SESSION` or `AuthMode.STATELESS` |
| `config` | `ConnectionConfig \| None` | Optional overrides for TLS, timeouts (see §6). Defaults apply if None |

---

### Behaviour

1. Validate all input parameters — raise `ValueError` on invalid inputs
2. Build the TLS context from `config` (or defaults)
3. Construct an `HttpClient` with the TLS context and timeout settings
4. Hand off to `AuthManager` to execute the chosen auth flow
5. Detect endpoint capabilities — GET `/redfish/v1`, parse `@odata.type`,
   detect short-form path structure
6. Construct and return `ClientContext` with all negotiated state

---

### AuthMode Enum

```
AuthMode.SESSION    — POST to SessionService; token stored in context
AuthMode.STATELESS  — credentials attached per-request; no session created
```

---

### Credentials Type (see §19)

A simple data class:

```
Credentials:
    username : str
    password : str
```

---

### Failure Behaviour

| Failure | Raised |
|---|---|
| Host unreachable | `RedfishConnectionError` |
| TLS certificate rejected | `RedfishTLSError` |
| Auth rejected (401/403) | `RedfishAuthError` |
| Endpoint not Redfish-compliant | `RedfishProtocolError` |
| Invalid parameters | `ValueError` |

---

## 5. ClientContext

### Module: `redfish_sdk/context.py`

---

### Purpose

The opaque handle returned to the caller. All subsequent SDK operations
go through this object. It carries all connection state internally.
It is never directly instantiated by the caller.

---

### Public Interface

```
ClientContext:

    # Connection state
    is_connected    : bool          (read-only property)
    base_url        : str           (read-only property — scheme + host + port)

    # Service handle access (lazy — instantiated on first access)
    event_service       : EventServiceHandle        (property)
    log_service         : LogServiceHandle          (property)
    telemetry_service   : TelemetryServiceHandle    (property)
    update_service      : UpdateServiceHandle       (property)
    discovery           : Discovery                 (property)

    # Direct / raw access — sync
    get(uri: str) -> RedfishResponse
    post(uri: str, body: dict) -> RedfishResponse
    patch(uri: str, body: dict) -> RedfishResponse
    delete(uri: str) -> RedfishResponse

    # Direct / raw access — async
    get_async(uri: str) -> Awaitable[RedfishResponse]
    post_async(uri: str, body: dict) -> Awaitable[RedfishResponse]
    patch_async(uri: str, body: dict) -> Awaitable[RedfishResponse]
    delete_async(uri: str) -> Awaitable[RedfishResponse]

    # Lifecycle
    close()                         -> None
    close_async()                   -> Awaitable[None]

    # Auth refresh — FR1.10
    refresh_auth()                  -> None
    refresh_auth_async()            -> Awaitable[None]
```

---

### Private State (Internal — Not Caller-Accessible)

| Attribute | Type | Description |
|---|---|---|
| `_http_client` | `HttpClient` | The transport layer instance |
| `_auth_state` | `AuthState` | Current auth mode + token or credentials |
| `_capabilities` | `EndpointCapabilities` | Negotiated at connect time |
| `_schema_cache` | `dict[str, dict]` | Schemas fetched from BMC, keyed by URI |
| `_discovery_map` | `dict[str, str]` | Service name → resolved URI from discovery |
| `_config` | `ConnectionConfig` | Effective config for this connection |
| `_service_handles` | `dict[str, Any]` | Lazy-loaded service handle instances |

---

### Lazy Service Handle Pattern

Service handles are not created at connect time. They are created on
first property access and cached in `_service_handles`.

```
@property
def event_service() -> EventServiceHandle:
    if 'event_service' not in _service_handles:
        _service_handles['event_service'] = EventServiceHandle(self)
    return _service_handles['event_service']
```

The service handle receives the `ClientContext` itself as its only
constructor argument — this gives it access to transport and state
without duplicating any parameters.

---

### Context Passed to Service Handles

Service handles receive the context and extract what they need internally:

```
EventServiceHandle(ctx: ClientContext):
    # internally uses ctx._http_client for transport
    # internally uses ctx._discovery_map to resolve the EventService URI
    # internally uses ctx._auth_state for auth attachment
```

This is the "Client Context as state carrier" pattern from AD3.

---

## 6. ConnectionConfig

### Module: `redfish_sdk/models/redfish_types.py`

---

### Purpose

An optional data class the caller can provide to `connect()` to override
defaults for TLS, timeouts, and path handling.

---

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `verify_tls` | `bool` | `True` | Strict TLS certificate validation |
| `tls_ca_cert` | `str \| None` | `None` | Path to custom CA certificate file |
| `connect_timeout_sec` | `float` | `10.0` | TCP connection timeout in seconds |
| `request_timeout_sec` | `float` | `30.0` | Per-request timeout in seconds |
| `task_poll_interval_sec` | `float` | `5.0` | Default task polling interval |
| `task_timeout_sec` | `float` | `300.0` | Default task completion timeout |
| `base_path_override` | `str \| None` | `None` | Override base path (e.g., `/redfish/v1`) |
| `allow_session_fallback` | `bool` | `False` | Retry stateless if session auth fails |
| `retry_on_connection_failure` | `int` | `0` | Extra TCP/TLS connection attempts before raising (FR1.8) |
| `retry_status_codes` | `list[int]` | `[]` | Retry request when server returns one of these HTTP status codes (FR1.9) |
| `retry_delay_sec` | `float` | `2.0` | Seconds to wait between retry attempts (FR1.8/FR1.9) |

---

## 7. Discovery

### Module: `redfish_sdk/discovery/discovery.py`  
### Accessed via: `ctx.discovery`

---

### Purpose

Traverses the Redfish resource tree at runtime and reports what is
available on the connected endpoint. Populates the context's
`_discovery_map` for use by service handles.

---

### Public Interface

```
Discovery:

    # Sync variants
    full()                  -> DiscoveryResult
    partial(service: str)   -> DiscoveryResult
    root()                  -> DiscoveryResult

    # Async variants
    full_async()                    -> Awaitable[DiscoveryResult]
    partial_async(service: str)     -> Awaitable[DiscoveryResult]
    root_async()                    -> Awaitable[DiscoveryResult]
```

---

### Discovery Modes

| Mode | Method | Behaviour |
|---|---|---|
| **Root** | `root()` | GET `/redfish/v1` only — enumerate top-level links, no traversal |
| **Partial** | `partial(service)` | GET ServiceRoot, then GET the named service URI only |
| **Full** | `full()` | GET ServiceRoot, then GET all top-level service links one level deep |

---

### DiscoveryResult

```
DiscoveryResult:
    services        : dict[str, str]   # service name → URI
    capabilities    : list[str]        # names of services found
    raw             : dict             # the raw ServiceRoot JSON

    # Query methods
    has_service(name: str)  -> bool
    service_uri(name: str)  -> str | None
```

---

### Side Effect

After any discovery call, the context's `_discovery_map` is updated
with the resolved service URIs. Service handles use this map to resolve
their target URI without re-fetching ServiceRoot.

---

### Service Names (Standard)

These are the standard service name strings used in discovery:

```
"EventService"
"LogService"
"TelemetryService"
"UpdateService"
"SessionService"
"AccountService"
"TaskService"
"Systems"
"Chassis"
"Managers"
```

---

## 8. RedfishResponse

### Module: `redfish_sdk/protocol/response.py`

---

### Purpose

The uniform response envelope returned by every public SDK operation.
Defined as a `pydantic` BaseModel for type safety and validation.

---

### Fields

| Field | Type | Description |
|---|---|---|
| `status_code` | `int` | HTTP status code |
| `success` | `bool` | True if `status_code` is in range 200–299 |
| `headers` | `dict[str, str]` | Response headers (lowercase keys) |
| `body` | `dict \| list \| None` | Parsed JSON body; None if response had no body |
| `extended_info` | `list[RedfishMessage]` | Entries from `@Message.ExtendedInfo` if present |
| `task` | `RedfishTask \| None` | Populated only when `status_code == 202` |
| `raw` | `str` | Raw response body as a string (for debugging or OEM use) |

---

### RedfishMessage (nested model)

| Field | Type | Description |
|---|---|---|
| `message_id` | `str` | The DMTF MessageId string (e.g., `Base.1.8.Success`) |
| `message` | `str` | Resolved human-readable message text |
| `severity` | `str` | `"OK"` / `"Warning"` / `"Critical"` |
| `resolution` | `str \| None` | Suggested resolution text if provided by BMC |
| `message_args` | `list[str]` | Arguments that were substituted into the message |

---

### Construction

`RedfishResponse` is constructed only inside the Protocol Layer — never
by service handles or callers directly. The construction flow is:

```
HttpClient executes request
    → raw httpx response
    → Protocol Layer extracts status, headers, body
    → ExtendedInfo entries parsed from body if present
    → If status == 202: TaskManager creates RedfishTask
    → RedfishResponse assembled and returned up the stack
```

---

## 9. RedfishTask and TaskManager

### Module: `redfish_sdk/protocol/task.py`

---

### Purpose

`RedfishTask` is the handle attached to a `RedfishResponse` when the BMC
responds with `202 Accepted`. `TaskManager` provides the polling logic
to wait for task completion.

---

### RedfishTask Interface

```
RedfishTask:
    task_uri        : str                  # URI of the Task resource
    task_id         : str                  # Task ID from the BMC
    state           : TaskState            # current known state
    percent_complete: int | None           # 0–100 or None if not reported
    messages        : list[RedfishMessage] # messages from the task

    # Sync — blocks until terminal state or timeout
    wait(
        poll_interval_sec : float | None = None,   # None = use config default
        timeout_sec       : float | None = None    # None = use config default
    ) -> RedfishResponse

    # Async — awaits until terminal state or timeout
    wait_async(
        poll_interval_sec : float | None = None,
        timeout_sec       : float | None = None
    ) -> Awaitable[RedfishResponse]

    # Async — callback-based monitoring
    monitor_async(
        on_state_change : Callable[[TaskState, RedfishTask], None],
        timeout_sec     : float | None = None
    ) -> Awaitable[None]

    # Cancel the task (if BMC supports it)
    cancel()        -> RedfishResponse
    cancel_async()  -> Awaitable[RedfishResponse]
```

---

### TaskState Enum

```
TaskState:
    NEW
    STARTING
    RUNNING
    SUSPENDED
    INTERRUPTED
    PENDING
    STOPPING
    COMPLETED
    KILLED
    EXCEPTION
    SERVICE
    CANCELLING
    CANCELLED
```

Terminal states (task polling stops): `COMPLETED`, `KILLED`, `EXCEPTION`,
`CANCELLED`.

---

### TaskManager (Internal)

`TaskManager` is not part of the public API. It is used internally by
`RedfishTask.wait()` and `RedfishTask.wait_async()`.

Behaviour:
1. Poll the task URI at `poll_interval_sec` intervals
2. Parse current `TaskState` and `PercentComplete` from each response
3. Update the `RedfishTask` state fields on each poll
4. Invoke `on_state_change` callback if registered (monitor mode)
5. Stop when a terminal state is reached or `timeout_sec` expires
6. On timeout: raise `RedfishTaskTimeoutError`
7. On terminal failure state: return the final `RedfishResponse` with
   the task's error details

---

## 10. MessageRegistry

### Module: `redfish_sdk/protocol/registry.py`

---

### Purpose

Fetches DMTF Message Registry files from the BMC and decodes `MessageId`
strings into human-readable messages.

---

### Interface

```
MessageRegistry:

    # Resolve a MessageId to a RedfishMessage
    resolve(message_id: str) -> RedfishMessage | None

    # Async variant
    resolve_async(message_id: str) -> Awaitable[RedfishMessage | None]

    # Pre-fetch a specific registry (optional — resolve auto-fetches)
    fetch(registry_prefix: str) -> bool
    fetch_async(registry_prefix: str) -> Awaitable[bool]
```

---

### MessageId Format

A Redfish `MessageId` has the form:
```
RegistryPrefix.MajorVersion.MinorVersion.MessageKey

Example: Base.1.8.Success
         OpenBMC.0.4.0.CPERError
         OCPRAS.1.0.0.RASEventOccurred
```

---

### Resolution Flow

```
resolve("Base.1.8.Success")
    │
    ├── Parse prefix "Base"
    ├── Check cache for "Base" registry
    │   ├── Hit  → look up "Success" in cached registry
    │   └── Miss → GET /redfish/v1/Registries/Base/Base.json
    │              → cache it
    │              → look up "Success"
    └── Format message text with any provided arguments
    → return RedfishMessage
```

---

### Cache

The registry cache is held inside the `MessageRegistry` instance, which
is itself held inside the `ClientContext._schema_cache`. Registries
persist for the lifetime of the context.

---

## 11. EventService Handle

### Module: `redfish_sdk/services/event_service.py`  
### Accessed via: `ctx.event_service`

---

### Purpose

Provides all EventService operations against the connected endpoint.

---

### URI Resolution

The EventService handle resolves its base URI in this priority order:
1. From `ctx._discovery_map["EventService"]` (if discovery was called)
2. By constructing `{base_url}/redfish/v1/EventService` as default

---

### Public Interface

```
EventServiceHandle:

    # Query the EventService resource itself
    get_service_info() -> RedfishResponse
    get_service_info_async() -> Awaitable[RedfishResponse]

    # Subscription management
    subscribe(
        destination     : str,
        event_types     : list[str] | None = None,
        registry_prefixes: list[str] | None = None,
        message_ids     : list[str] | None = None,
        resource_types  : list[str] | None = None,     # FR5.1 v0.3
        event_format_type: str | None = None,           # FR5.1 v0.3
        context         : str | None = None,
        protocol        : str = "Redfish",
        subscription_type: str = "RedfishEvent"
    ) -> RedfishResponse
    subscribe_async(...) -> Awaitable[RedfishResponse]

    list_subscriptions()  -> RedfishResponse
    list_subscriptions_async() -> Awaitable[RedfishResponse]

    get_subscription(subscription_uri: str) -> RedfishResponse
    get_subscription_async(subscription_uri: str) -> Awaitable[RedfishResponse]

    delete_subscription(subscription_uri: str) -> RedfishResponse
    delete_subscription_async(subscription_uri: str) -> Awaitable[RedfishResponse]

    # SSE streaming — returns an async generator of RedfishEvent
    subscribe_sse(
        filters : dict | None = None
    ) -> AsyncGenerator[RedfishEvent, None]

    # Submit a test event (simulator and test use)
    submit_test_event(event_data: dict) -> RedfishResponse
    submit_test_event_async(event_data: dict) -> Awaitable[RedfishResponse]
```

---

### RedfishEvent (for SSE)

```
RedfishEvent:
    event_id        : str
    event_type      : str
    event_timestamp : str
    message_id      : str
    message         : str           # decoded via MessageRegistry
    severity        : str
    origin_of_condition : str | None
    raw             : dict          # full raw event JSON preserved
```

---

## 12. LogService Handle

### Module: `redfish_sdk/services/log_service.py`  
### Accessed via: `ctx.log_service`

---

### Purpose

Provides access to any `LogService` on the connected endpoint. A BMC
may have multiple log services (System EventLog, Manager log, CPERLogs).
The handle supports accessing any of them by URI.

---

### URI Resolution

Default target: `{base_url}/redfish/v1/Systems/{system_id}/LogServices`

For named log services, the caller provides the service URI or name.

---

### Public Interface

```
LogServiceHandle:

    # List available log services on the BMC
    list_services() -> RedfishResponse
    list_services_async() -> Awaitable[RedfishResponse]

    # Get all entries from a specific log service
    get_entries(
        log_service_uri : str,
        filter          : LogFilter | None = None
    ) -> RedfishResponse
    get_entries_async(
        log_service_uri : str,
        filter          : LogFilter | None = None
    ) -> Awaitable[RedfishResponse]

    # Get a single log entry
    get_entry(entry_uri: str) -> RedfishResponse
    get_entry_async(entry_uri: str) -> Awaitable[RedfishResponse]

    # Clear a log service
    clear_log(log_service_uri: str) -> RedfishResponse
    clear_log_async(log_service_uri: str) -> Awaitable[RedfishResponse]

    # SEL binary record parsing — FR6.6 (module-level function, not a method)
    # parse_sel_entry(raw_hex: str) -> ParsedSelRecord
    # Accepts three formats:
    #   1. Plain hex:                 "b70fcad117db6837010000002000FFFF"
    #   2. OpenBMC prefix:            "Raw Data : Hex <hex>"  (from LogEntry.MessageArgs[0])
    #   3. Flat generator prefix:     "Raw data: <hex>"       (from event generator SEL replay — FR6.6 v0.3)
    # Raises RedfishSDKError on invalid / too-short input
```

---

### ParsedSelRecord (FR6.6)

```
ParsedSelRecord:
    record_type     : str           # "PxeBoot" | "HostOsModeChange" | "HostOsHandOff" | "Unknown"
    record_id       : int           # 16-bit LE from bytes 0-1
    timestamp_raw   : int           # Unix epoch from bytes 3-6 LE
    raw_hex         : str           # normalised uppercase hex (32 chars = 16 bytes)
    raw_bytes       : list[int]
    sensor_type     : int | None
    sensor_number   : int | None
    event_dir_type  : int | None
    event_data      : list[int]
    description     : str
```

SEL record type byte decoding (OpenBMC OEM timestamped events):

| Byte 2 (record type) | Byte 13 (subtype) | `record_type` |
|---|---|---|
| `0xCA` | — | `"PxeBoot"` |
| `0xD9` | `0x01` | `"HostOsModeChange"` |
| `0xD9` | `0x02` | `"HostOsHandOff"` |
| anything else | — | `"Unknown"` |

---

### LogFilter

```
LogFilter:
    severity        : str | None         # "OK" | "Warning" | "Critical"
    start_time      : str | None         # ISO 8601 timestamp
    end_time        : str | None         # ISO 8601 timestamp
    message_id      : str | None         # filter by MessageId prefix
    max_entries     : int | None         # limit result count
```

---

## 13. TelemetryService Handle

### Module: `redfish_sdk/services/telemetry_service.py`  
### Accessed via: `ctx.telemetry_service`

---

### Purpose

Provides access to the TelemetryService — metric definitions, metric
reports, and streaming telemetry via SSE.

---

### URI Resolution

Default: `{base_url}/redfish/v1/TelemetryService`

---

### Public Interface

```
TelemetryServiceHandle:

    # Query service info
    get_service_info() -> RedfishResponse
    get_service_info_async() -> Awaitable[RedfishResponse]

    # Metric Report Definitions
    list_metric_report_definitions() -> RedfishResponse
    list_metric_report_definitions_async() -> Awaitable[RedfishResponse]

    get_metric_report_definition(definition_uri: str) -> RedfishResponse
    get_metric_report_definition_async(definition_uri: str) -> Awaitable[RedfishResponse]

    # Metric Reports
    list_metric_reports() -> RedfishResponse
    list_metric_reports_async() -> Awaitable[RedfishResponse]

    get_metric_report(report_uri: str) -> RedfishResponse
    get_metric_report_async(report_uri: str) -> Awaitable[RedfishResponse]

    # Streaming telemetry via SSE — async generator
    stream_metric_reports(
        definition_uri : str | None = None
    ) -> AsyncGenerator[MetricReport, None]
```

---

### MetricReport (for streaming)

```
MetricReport:
    report_id       : str
    report_uri      : str
    timestamp       : str
    metric_values   : list[MetricValue]
    raw             : dict

MetricValue:
    metric_id       : str
    metric_value    : str | float | int
    timestamp       : str
    metric_property : str | None
```

---

## 14. UpdateService Handle

### Module: `redfish_sdk/services/update_service.py`  
### Accessed via: `ctx.update_service`

---

### Purpose

Provides access to UpdateService — firmware/software inventory and
update operations. Update operations that return 202 surface a
`RedfishTask` via the standard `RedfishResponse.task` field.

---

### URI Resolution

Default: `{base_url}/redfish/v1/UpdateService`

---

### Public Interface

```
UpdateServiceHandle:

    # Query service info
    get_service_info() -> RedfishResponse
    get_service_info_async() -> Awaitable[RedfishResponse]

    # Firmware Inventory
    list_firmware_inventory() -> RedfishResponse
    list_firmware_inventory_async() -> Awaitable[RedfishResponse]

    get_firmware_component(component_uri: str) -> RedfishResponse
    get_firmware_component_async(component_uri: str) -> Awaitable[RedfishResponse]

    # Software Inventory
    list_software_inventory() -> RedfishResponse
    list_software_inventory_async() -> Awaitable[RedfishResponse]

    get_software_component(component_uri: str) -> RedfishResponse
    get_software_component_async(component_uri: str) -> Awaitable[RedfishResponse]

    # Initiate update — returns RedfishResponse; response.task populated if 202
    simple_update(
        image_uri       : str,
        targets         : list[str] | None = None,
        transfer_protocol: str | None = None,
        apply_time      : str | None = None
    ) -> RedfishResponse
    simple_update_async(...) -> Awaitable[RedfishResponse]

    # Multipart firmware push — FR7.5
    # Fetches UpdateService to discover MultipartHttpPushUri / HttpPushUri,
    # then POSTs the file as multipart/form-data.
    # Raises RedfishHTTPError if UpdateService is unreachable (non-200).
    # Raises RedfishProtocolError if no push URI is advertised.
    push_firmware(
        local_path  : str,                  # path to local firmware file
        targets     : list[str] | None = None,
        apply_time  : str | None = None
    ) -> RedfishResponse                    # 202 + response.task if accepted
    push_firmware_async(...) -> Awaitable[RedfishResponse]
```

---

## 15. RedfishEventListener

### Module: `redfish_sdk/events/listener.py`  
### Exported via: `redfish_sdk/__init__.py`

---

### Purpose

A standalone embedded HTTP server that receives push event deliveries
from the BMC. Independent lifecycle — not owned by `ClientContext`.
Can be wired to a context for `MessageRegistry` decoding.

---

### Public Interface

```
RedfishEventListener:

    __init__(
        port            : int,
        host            : str = "0.0.0.0",
        tls_cert        : str | None = None,    # path to cert file
        tls_key         : str | None = None,    # path to key file
        context         : str | None = None,    # expected subscription context — FR5.3
        buffer_size     : int = 200             # max buffered events — FR5.3
    )

    # Wire to a context for message registry decoding (optional)
    use_context(ctx: ClientContext) -> None

    # Register event callbacks
    on_event(
        callback : Callable[[RedfishEvent], None]
                   | Callable[[RedfishEvent], Awaitable[None]]
    ) -> None

    # Register callbacks filtered by EventType
    on_event_type(
        event_type : str,
        callback   : Callable[[RedfishEvent], None]
                     | Callable[[RedfishEvent], Awaitable[None]]
    ) -> None

    # Register callbacks filtered by MessageId prefix
    on_registry(
        registry_prefix : str,
        callback        : Callable[[RedfishEvent], None]
                          | Callable[[RedfishEvent], Awaitable[None]]
    ) -> None

    # Lifecycle — sync
    start() -> None     # non-blocking — starts background asyncio server
    stop()  -> None     # graceful shutdown

    # Lifecycle — async
    start_async() -> Awaitable[None]
    stop_async()  -> Awaitable[None]

    # State
    is_running  : bool  (property)
    listen_url  : str   (property — e.g., "http://0.0.0.0:9090")

    # Buffered events retrieval — FR5.3
    get_buffered_events() -> list[RedfishEvent]

    # Per-source-IP event counts — FR5.3
    get_ip_stats() -> dict[str, int]
```

---

### Event Delivery Flow

```
BMC sends HTTP POST to listener port
    │
    ▼
Listener receives request; records reception wall-clock time
    │
    ▼
Parse Redfish event JSON payload
    │
    ├── Context validation (FR5.3):
    │       if listener.context is set:
    │           compare event["Context"] to listener.context
    │           → mismatch: respond 204, stop processing
    │
    ├── Latency logging (FR5.3):
    │       parse event["EventTimestamp"] (ISO 8601)
    │       delta_ms = reception_time − event_time
    │       log DEBUG "event latency %d ms" % delta_ms
    │
    ├── Per-IP counter (FR5.3):
    │       ip_stats[source_ip] += 1
    │
    ├── If context is wired:
    │       resolve MessageId via MessageRegistry
    │
    ▼
Construct RedfishEvent object
    │
    ▼
Append to ring buffer (up to buffer_size events)
    │
    ▼
Match against registered callbacks:
    ├── All on_event() callbacks
    ├── Matching on_event_type() callbacks
    └── Matching on_registry() callbacks
    │
    ▼
Invoke all matched callbacks
(sync callbacks called directly;
 async callbacks scheduled on event loop)
    │
    ▼
Respond 204 No Content to BMC
```

---

### TLS Support

If `tls_cert` and `tls_key` are provided, the listener starts as an
HTTPS server. This matches what real BMC EventServices expect when
delivering push events to an HTTPS destination.

---

## 16. Transport Layer — HttpClient

### Module: `redfish_sdk/transport/http_client.py`

---

### Purpose

Provides the transport abstraction layer (NFR8.2). Three classes:

- **`HttpClient`** (ABC) — injectable interface; all SDK layers depend on this type only.
- **`DefaultHttpClient`** — production implementation wrapping `httpx`; handles retry (FR1.8, FR1.9) and multipart upload (FR7.5).
- **`MockHttpClient`** — in-memory test double; returns canned `RawHttpResponse` values keyed by `(METHOD, path)`; no network required.

Never imported directly by callers outside the transport layer.

---

### Internal Interface (used by Protocol and Service layers)

```
HttpClient (ABC):

    # Core request methods — async
    request_async(
        method   : str,             # "GET" | "POST" | "PATCH" | "DELETE"
        path     : str,             # relative path e.g. "/redfish/v1/Systems"
        headers  : dict | None,
        body     : dict | None
    ) -> RawHttpResponse

    # Multipart upload — FR7.5
    request_multipart_async(
        method   : str,
        path     : str,
        headers  : dict | None,
        files    : dict             # httpx files= format
    ) -> RawHttpResponse

    # Sync wrappers
    request(...) -> RawHttpResponse

    close_async() -> Awaitable[None]
    close()       -> None


DefaultHttpClient(HttpClient):

    __init__(
        base_url    : str,
        tls_config  : TLSConfig,
        timeouts    : TimeoutConfig,
        config      : ConnectionConfig | None   # reads retry fields
    )

    # Retry logic (FR1.8, FR1.9):
    #   - ConnectError/ConnectTimeout: retry up to retry_on_connection_failure times
    #   - HTTP status in retry_status_codes: retry with the same count
    #   - retry_delay_sec sleep between attempts
    # Logging: debug on each attempt, warning on failure, error when all attempts fail


MockHttpClient(HttpClient):

    __init__(responses: dict[tuple[str,str], RawHttpResponse] | None)
    register(method: str, path: str, response: RawHttpResponse) -> None
    # Unregistered (method, path) → HTTP 404
```
    close() -> None
```

---

### RawHttpResponse (internal type)

Not exposed publicly. Used only between Transport and Protocol layers.

```
RawHttpResponse:
    status_code : int
    headers     : dict[str, str]
    body_text   : str
    body_json   : dict | list | None    # parsed if Content-Type is JSON
```

---

### Responsibilities of HttpClient

- Maintain a single `httpx.AsyncClient` instance for connection reuse
- Attach standard Redfish headers to every request:
  - `OData-Version: 4.0`
  - `Content-Type: application/json`
  - `Accept: application/json`
- Execute the request and return `RawHttpResponse`
- Auth header attachment is **not** done here — done by `AuthManager`

---

## 17. Transport Layer — AuthManager

### Module: `redfish_sdk/transport/auth.py`

---

### Purpose

Internal module. Executes the chosen auth flow at connect time and
manages ongoing auth attachment for subsequent requests.

---

### Internal Interface

```
AuthManager:

    __init__(
        http_client     : HttpClient,
        credentials     : Credentials,
        auth_mode       : AuthMode
    )

    # Execute the auth flow — called once at connect time
    authenticate_async() -> Awaitable[AuthState]
    authenticate() -> AuthState

    # Attach auth to an outbound request's headers
    attach_auth(headers: dict) -> dict

    # Terminate session (session mode only)
    logout_async() -> Awaitable[None]
    logout() -> None
```

---

### AuthState (internal type)

```
AuthState:
    mode            : AuthMode
    session_token   : str | None    # populated for SESSION mode
    session_uri     : str | None    # URI to DELETE on logout
    credentials     : Credentials  # kept for STATELESS mode
```

---

### Session Auth Flow

```
authenticate() — SESSION mode:
    POST {base_url}/redfish/v1/SessionService/Sessions
    body: { "UserName": username, "Password": password }
    →  201 Created
    →  Extract X-Auth-Token header → session_token
    →  Extract Location header → session_uri
    →  Store in AuthState
```

---

### Stateless Auth Flow

```
authenticate() — STATELESS mode:
    GET {base_url}/redfish/v1
    with Basic Auth header
    →  200 OK (validates endpoint is reachable and creds are accepted)
    →  Store credentials in AuthState for per-request attachment
```

---

### Auth Attachment

```
attach_auth(headers) — SESSION mode:
    headers["X-Auth-Token"] = auth_state.session_token
    return headers

attach_auth(headers) — STATELESS mode:
    encode credentials as HTTP Basic Auth
    headers["Authorization"] = "Basic {encoded}"
    return headers
```

---

## 18. Transport Layer — TLS

### Module: `redfish_sdk/transport/tls.py`

---

### Purpose

Builds the TLS configuration passed to `httpx` based on `ConnectionConfig`.

---

### Internal Interface

```
build_tls_config(config: ConnectionConfig) -> TLSConfig

TLSConfig:
    verify      : bool | str    # False = bypass; str = path to CA cert; True = system CAs
    cert        : tuple | None  # (client_cert_path, client_key_path) if mTLS
```

---

### Mapping from ConnectionConfig

| `ConnectionConfig` field | `TLSConfig.verify` value |
|---|---|
| `verify_tls=True`, no CA cert | `True` (system CA store) |
| `verify_tls=True`, `tls_ca_cert` set | `tls_ca_cert` path string |
| `verify_tls=False` | `False` (bypass — dev/test only) |

---

## 19. Internal Data Contracts

These types are used internally across modules and defined in
`redfish_sdk/models/redfish_types.py`.

### Credentials

```
Credentials:
    username    : str
    password    : str
```

### AuthMode

```
AuthMode (Enum):
    SESSION     = "session"
    STATELESS   = "stateless"
```

### EndpointCapabilities

```
EndpointCapabilities:
    redfish_version     : str           # e.g. "1.15.0"
    odata_version       : str           # e.g. "4.0"
    short_form          : bool          # True if /v1 style paths
    base_path           : str           # e.g. "/redfish/v1"
    available_services  : list[str]     # service names found at ServiceRoot
```

### TimeoutConfig

```
TimeoutConfig:
    connect_sec     : float
    request_sec     : float
    task_poll_sec   : float
    task_timeout_sec: float
```

---

## 20. Error Design

### Philosophy

The SDK surfaces errors as Python exceptions. The SDK does not make
assumptions about how callers handle errors — callers decide whether to
catch, propagate, or log them.

### Exception Hierarchy

```
RedfishSDKError                     (base for all SDK exceptions)
├── RedfishConnectionError          (network / TCP failure)
├── RedfishTLSError                 (certificate error)
├── RedfishAuthError                (401, 403, session failure)
├── RedfishProtocolError            (endpoint not Redfish-compliant)
├── RedfishHTTPError                (4xx or 5xx response)
│   ├── status_code : int
│   └── response    : RedfishResponse
├── RedfishTaskTimeoutError         (task did not complete in time)
│   └── task        : RedfishTask
├── RedfishTaskFailedError          (task reached exception/killed state)
│   └── task        : RedfishTask
└── RedfishNotFoundError            (resource not found — 404)
```

### What Raises vs What Returns

| Situation | SDK Behaviour |
|---|---|
| Network failure | Raises `RedfishConnectionError` |
| TLS cert rejected | Raises `RedfishTLSError` |
| 401/403 response | Raises `RedfishAuthError` |
| 404 response | Returns `RedfishResponse` with `success=False`, `status_code=404` |
| 4xx/5xx response | Returns `RedfishResponse` with `success=False` |
| Successful 2xx | Returns `RedfishResponse` with `success=True` |
| 202 Accepted | Returns `RedfishResponse` with `task` populated |
| Task timeout | Raises `RedfishTaskTimeoutError` |
| Task failed state | Raises `RedfishTaskFailedError` |
| Missing optional resource | Returns `RedfishResponse` with empty `body` |

### Key Design Decision

**404 is not an exception.** It is a valid Redfish response meaning
the resource does not exist. The caller receives a `RedfishResponse`
and decides how to treat it. This supports NFR5.3 (missing optional
resources return empty results, not errors).

---

## 21. Async and Sync Bridge

### Pattern

All business logic is written once as `async def` functions. Sync
variants are wrappers that call the async implementation using
`asyncio.run()` or a managed event loop.

### Naming Convention

| Layer | Async method | Sync method |
|---|---|---|
| `connect()` | `connect_async(...)` | `connect(...)` |
| `ClientContext` | `get_async(uri)` | `get(uri)` |
| Service handles | `subscribe_async(...)` | `subscribe(...)` |
| Discovery | `full_async()` | `full()` |
| TaskManager | `wait_async(...)` | `wait(...)` |

### asyncio.run() Usage

The sync bridge uses `asyncio.run()` when no event loop is running.
If an event loop is already running (e.g., inside a Jupyter notebook),
the sync bridge must detect this and raise a clear error message
directing the caller to use the `_async` variant instead.

---

## 22. Sequence Diagrams

### SD1 — Session Connect

```
Caller                  SDK                 BMC
  │                      │                   │
  │──connect(host,       │                   │
  │   creds, SESSION)───►│                   │
  │                      │──TCP + TLS───────►│
  │                      │◄──TLS handshake───│
  │                      │                   │
  │                      │──POST /redfish/v1/│
  │                      │  SessionService/  │
  │                      │  Sessions─────────►│
  │                      │◄──201 + Token─────│
  │                      │                   │
  │                      │──GET /redfish/v1──►│
  │                      │◄──200 ServiceRoot─│
  │                      │  (parse caps)     │
  │                      │                   │
  │◄──ClientContext───────│                   │
```

---

### SD2 — Service Call (Log Service)

```
Caller          ClientContext    LogServiceHandle   HttpClient      BMC
  │                  │                  │               │             │
  │──ctx.log_service─►│                  │               │             │
  │◄──handle(lazy)───│                  │               │             │
  │                  │                  │               │             │
  │──handle.get_entries(uri, filter)───►│               │             │
  │                  │                  │──request()───►│             │
  │                  │                  │  (with auth)  │──GET───────►│
  │                  │                  │               │◄──200 JSON──│
  │                  │                  │◄──RawResponse─│             │
  │                  │                  │               │             │
  │                  │    (build RedfishResponse)       │             │
  │◄──RedfishResponse────────────────────│               │             │
```

---

### SD3 — Event Subscribe and Receive

```
Caller          EventServiceHandle    Listener        BMC
  │                    │                  │             │
  │──subscribe(dest)──►│                  │             │
  │                    │──POST /EventService/Subscriptions──────────►│
  │                    │◄──201 Created────────────────────────────────│
  │◄──RedfishResponse──│                  │             │
  │                    │                  │             │
  │──listener.on_event(cb)               │             │
  │──listener.start()─────────────────►  │             │
  │                    │                  │             │
  │                    │                  │◄──POST event│
  │                    │                  │ (from BMC)  │
  │                    │    (parse, decode MessageId)   │
  │◄──callback(RedfishEvent)─────────────│             │
  │                    │                  │──204────────►│
```

---

### SD4 — Task Polling

```
Caller          UpdateServiceHandle    TaskManager     BMC
  │                    │                   │             │
  │──simple_update(──►│                   │             │
  │   image_uri)       │──POST SimpleUpdate────────────►│
  │                    │◄──202 + Task URI───────────────│
  │                    │  (create RedfishTask)          │
  │◄──RedfishResponse──│                   │             │
  │   (with .task)     │                   │             │
  │                    │                   │             │
  │──response.task.wait()                 │             │
  │─────────────────────────────────────►│             │
  │                    │                   │──GET Task──►│
  │                    │                   │◄──Running───│
  │                    │            (wait poll_interval) │
  │                    │                   │──GET Task──►│
  │                    │                   │◄──Completed─│
  │◄──final RedfishResponse───────────────│             │
```

---

## 23. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — Python design |
| 0.2 | 2026-03-05 | Hari | Add retry (FR1.8/FR1.9), refresh_auth (FR1.10), HttpClient→ABC+DefaultHttpClient+MockHttpClient (NFR8.2), SEL parsing in LogService (FR6.6), multipart in UpdateService (FR7.5), logging instrumentation (NFR8.1) |
| 0.3 | 2026-03-07 | Copilot | §11 subscribe() gains `resource_types` + `event_format_type` (FR5.1); §12 parse_sel_entry flat format (FR6.6); §15 EventListener interface + flow updated: `context` validation, latency logging, per-IP counter, ring buffer + `get_buffered_events()` / `get_ip_stats()` (FR5.3) |
