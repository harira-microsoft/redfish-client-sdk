# Redfish Client SDK — Python Architecture

**Document ID:** RSDK-ARCH-002  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Base Architecture:** RSDK-ARCH-001  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Python-Specific Architectural Goals](#2-python-specific-architectural-goals)
3. [Technology Choices](#3-technology-choices)
4. [Package Structure](#4-package-structure)
5. [Component Expression in Python](#5-component-expression-in-python)
6. [Async and Sync Model in Python](#6-async-and-sync-model-in-python)
7. [ClientContext in Python](#7-clientcontext-in-python)
8. [RedfishResponse in Python](#8-redfishresponse-in-python)
9. [Event Listener in Python](#9-event-listener-in-python)
10. [Packaging and Distribution](#10-packaging-and-distribution)
11. [Relationship to bmc-redfish-simulator](#11-relationship-to-bmc-redfish-simulator)
12. [Change History](#12-change-history)

---

## 1. Purpose

This document defines the Python-specific architecture for Phase 1 of the
Redfish Client SDK. It takes the language-independent architecture
(RSDK-ARCH-001) as its foundation and expresses every component and decision
idiomatically in Python.

The Python implementation is the **Phase 1 delivery** and serves as the
**API design reference** for the C++ (Phase 2) and Rust (Phase 3)
implementations.

---

## 2. Python-Specific Architectural Goals

| Goal | Rationale |
|---|---|
| Async-first, sync as a wrapper | Python's `asyncio` ecosystem is best served by async-native design |
| Full type hints throughout | Explicit API surface — serves as design reference for C++ and Rust |
| `pydantic` for structured responses | Schema validation, serialization, and IDE support at no extra cost |
| Single `httpx` client for both sync and async | One HTTP library, two modes — avoids duplicating transport logic |
| pip installable, zero native dependencies | Easy adoption — no build tools required for Python users |

---

## 3. Technology Choices

### Core Dependencies

| Concern | Library | Reason |
|---|---|---|
| HTTP transport (async) | `httpx` (async client) | Native async, HTTP/1.1 and HTTP/2, clean API |
| HTTP transport (sync) | `httpx` (sync client) | Same library — no separate sync dependency |
| TLS / certificate handling | Built into `httpx` | Supports both strict and bypass modes |
| Response modelling | `pydantic` v2 | Type-safe, validated, IDE-friendly models |
| Async runtime | `asyncio` (stdlib) | No external async framework needed |
| JSON parsing | `stdlib json` + `pydantic` | Standard library, no additional dependency |
| Event Listener server | `aiohttp` or `asyncio` HTTP server | Lightweight embedded server for push event reception |

### Development / Build Dependencies

| Concern | Library | Reason |
|---|---|---|
| Packaging | `pyproject.toml` + `hatchling` | Modern Python packaging standard |
| Testing | `pytest` + `pytest-asyncio` | Industry standard, async test support |
| Type checking | `mypy` | Validate type hints across the SDK |
| Linting | `ruff` | Fast, modern Python linter |

---

## 4. Package Structure

```
RedfishClientSDK/
└── python/
    ├── pyproject.toml              # Package metadata and dependencies
    ├── README.md                   # Python SDK quick-start
    │
    ├── redfish_sdk/                # Main installable package
    │   ├── __init__.py             # Public API surface — exports connect()
    │   │
    │   ├── client.py               # SDK Entry Point — connect() function
    │   ├── context.py              # ClientContext — the opaque handle
    │   │
    │   ├── discovery/
    │   │   ├── __init__.py
    │   │   └── discovery.py        # Full / partial / root discovery
    │   │
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── event_service.py    # EventService handle
    │   │   ├── log_service.py      # LogService handle
    │   │   ├── telemetry_service.py # TelemetryService handle
    │   │   └── update_service.py   # UpdateService handle
    │   │
    │   ├── events/
    │   │   ├── __init__.py
    │   │   └── listener.py         # RedfishEventListener — standalone
    │   │
    │   ├── protocol/
    │   │   ├── __init__.py
    │   │   ├── response.py         # RedfishResponse model
    │   │   ├── task.py             # RedfishTask and TaskManager
    │   │   └── registry.py         # MessageRegistry — decode MessageId
    │   │
    │   ├── transport/
    │   │   ├── __init__.py
    │   │   ├── http_client.py      # httpx wrapper — async and sync
    │   │   ├── auth.py             # AuthManager — session and stateless
    │   │   └── tls.py              # TLS configuration
    │   │
    │   └── models/
    │       ├── __init__.py
    │       └── redfish_types.py    # Pydantic models for Redfish resources
    │
    ├── samples/                    # Runnable sample clients
    │   ├── README.md
    │   ├── 01_connect_discover.py
    │   ├── 02_partial_discover.py
    │   ├── 03_get_resources.py
    │   ├── 04_direct_api.py
    │   ├── 05_event_subscribe.py
    │   ├── 06_event_listener.py
    │   ├── 07_event_monitor.py
    │   ├── 08_log_service.py
    │   ├── 09_telemetry.py
    │   ├── 10_update_service.py
    │   ├── 11_task_polling.py
    │   └── 12_session_vs_stateless.py
    │
    └── tests/
        ├── unit/
        └── integration/
```

---

## 5. Component Expression in Python

### SDK Entry Point → `client.py`

A module-level `connect()` function. Not a class constructor. The caller
never instantiates anything — they call a function and receive a handle.

The function has both sync and async variants:

- `connect(...)` — synchronous, blocks until connection is established
- `connect_async(...)` — async, awaitable

---

### ClientContext → `context.py`

A Python class. Its internal attributes are private (name-mangled or
prefixed with `_`). The class exposes only the service handles and
operation methods as its public interface.

The context class is **not directly instantiated by the caller**. It is
constructed only by `connect()` / `connect_async()`.

Properties on the context:
- `discovery` — the Discovery component
- `event_service` — the EventService handle
- `log_service` — the LogService handle
- `telemetry_service` — the TelemetryService handle
- `update_service` — the UpdateService handle
- `get(uri)` / `post(uri, body)` / `patch(uri, body)` / `delete(uri)` — direct access
- All methods available in both sync and async variants

---

### Discovery → `discovery/discovery.py`

A class accessed via `ctx.discovery`. Three call patterns:

- `ctx.discovery.full()` — traverse entire service tree
- `ctx.discovery.partial(service_name)` — single node only
- `ctx.discovery.root()` — ServiceRoot links only

Returns an inspectable `DiscoveryResult` object. Also populates the
context's internal service URI map for subsequent calls.

---

### Service Handles → `services/`

Each service handle is a class. Each is accessed as a property on the
`ClientContext`. They are constructed lazily — not created until first
accessed.

Each handle exposes intent-driven methods that return `RedfishResponse`.
All methods available in both sync and async variants.

The **Log Service Handle** (`log_service`) accepts a `LogFilter` dataclass
carrying `top`, `skip`, `severity`, `message_id`, and `odata_filter` fields.
The handle builds the OData query string in the required order
(`$skip` → `$top` → `$filter`) and provides `iter_entries_async()` —
an async generator that follows `Members@odata.nextLink` across pages
without caller-managed offset tracking.

---

### Protocol Layer → `protocol/`

Three modules:

- `response.py` — `RedfishResponse` as a pydantic model
- `task.py` — `RedfishTask` handle and `TaskManager` that polls task URIs
- `registry.py` — `MessageRegistry` that fetches and caches DMTF registries
  from the BMC and decodes `MessageId` strings

---

### Transport Layer → `transport/`

Three modules — all private, never imported by callers:

- `http_client.py` — wraps `httpx` AsyncClient and Client, exposes a
  uniform internal request interface
- `auth.py` — implements both session and stateless auth flows
- `tls.py` — constructs the `httpx` SSL context from the connection config

---

### Event Listener → `events/listener.py`

A standalone class `RedfishEventListener`. Not accessed via the
`ClientContext`. Instantiated directly by the caller with a port number.
Wired to a context via `listener.use_context(ctx)` for registry decoding.

Internally runs an `asyncio`-based HTTP server. Start / stop methods
are provided in both sync and async variants.

---

## 6. Async and Sync Model in Python

### The Pattern

All SDK operations are implemented **once as async** using `asyncio` and
`httpx` async client. The sync variant is a thin wrapper that drives the
async implementation to completion using a managed event loop.

```
Async implementation   ◄── single source of logic
        │
        ▼
Sync wrapper           ◄── calls async via event loop run
```

This ensures no business logic is duplicated between sync and async paths.

### Naming Convention

Both variants exist on every method:

| Async variant | Sync variant |
|---|---|
| `await ctx.get(uri)` | `ctx.get_sync(uri)` |
| `await ctx.event_service.subscribe(...)` | `ctx.event_service.subscribe_sync(...)` |
| `await connect_async(...)` | `connect(...)` |

The async variant is always the primary. The sync variant is always
suffixed with `_sync` to make the distinction explicit.

---

## 7. ClientContext in Python

### Construction (Internal Only)

The `ClientContext` object is constructed inside `connect()` after all
negotiation is complete. It is never exposed as a class for the caller
to import or instantiate.

### Private Internals

All internal state is held in private attributes:

| Attribute | Contents |
|---|---|
| `_http_client` | The `httpx` client instance |
| `_auth_state` | Current auth mode and token / credentials |
| `_capabilities` | Negotiated endpoint capabilities |
| `_schema_cache` | Dict of fetched schemas, keyed by URI |
| `_discovery_map` | Dict of service name → resolved URI |
| `_config` | Timeouts, TLS settings, base URL |

### Public Interface

Only the following are part of the public API on `ClientContext`:

- Service handle properties (`event_service`, `log_service`, etc.)
- `discovery` property
- Direct access methods (`get`, `post`, `patch`, `delete`)
- `close()` / `close_async()` — terminate the session and close transport
- `is_connected` — boolean property

---

## 8. RedfishResponse in Python

Expressed as a `pydantic` BaseModel for type safety and IDE support.

### Fields

| Field | Type | Description |
|---|---|---|
| `status_code` | `int` | HTTP status code |
| `success` | `bool` | True if status_code is 2xx |
| `headers` | `dict[str, str]` | Response headers |
| `body` | `dict \| list \| None` | Parsed JSON body |
| `extended_info` | `list[RedfishMessage]` | Redfish `@Message.ExtendedInfo` entries |
| `task` | `RedfishTask \| None` | Present if response was 202 Accepted |
| `raw` | `str` | Raw response body string |

### RedfishMessage (nested)

| Field | Type | Description |
|---|---|---|
| `message_id` | `str` | The DMTF MessageId string |
| `message` | `str` | Human-readable message text |
| `severity` | `str` | OK / Warning / Critical |
| `resolution` | `str \| None` | Suggested resolution if provided |

---

## 9. Event Listener in Python

### Lifecycle

The `RedfishEventListener` is a standalone class. Its lifecycle is:

```
listener = RedfishEventListener(port=9090, context="RSDK-Subs-01")
listener.use_context(ctx)          # wire to context for registry decoding
listener.on_event(callback_fn)     # register callback
listener.start()                   # begin listening (background thread)
...
listener.stop()                    # stop listening
```

### Event Delivery

When the BMC POSTs an event to the listener:

1. Listener receives the HTTP POST; records reception timestamp
2. Parses the Redfish event payload
3. **Context validation (FR5.3):** if a `context` string was set at construction,
   the event's `Context` field is compared — on mismatch the listener responds
   `204 No Content` without firing any callbacks
4. **Latency logging:** the event's `EventTimestamp` field is compared to the
   reception wall-clock time and the delta is logged at DEBUG level
5. **Per-IP counter:** the source IP of the POST is counted in an in-memory dict
6. Resolves `MessageId` via `MessageRegistry` if context is wired
7. Constructs a `RedfishEvent` object
8. Appends to the in-memory event buffer (bounded ring buffer, default 200 events)
9. Invokes all registered callbacks with the `RedfishEvent`
10. Responds `204 No Content` to the BMC

Callbacks can be sync or async functions — the listener handles both.

### GET endpoint (buffered event retrieval)

`GET <listen_path>` returns a JSON array of the most recently buffered events.
This provides a polling fallback for callers that cannot receive push deliveries
from inside a callback context.

### MetricReport events

Events with `EventFormatType == "MetricReport"` are parsed along a separate
path that extracts `MetricReport` fields.  They are delivered to the same
callback set but the `RedfishEvent.raw` dict will contain the full report.

### Implementation (Python)

- `aiohttp` embedded server runs on a dedicated `asyncio` event loop spawned
  on a background `threading.Thread`
- Per-connection concurrency is handled by `aiohttp` natively
- `start()` blocks until the server is accepting connections (up to 10 s)
- `stop()` calls `loop.stop()` then joins the thread with a 5 s timeout
- TLS: optional `ssl.SSLContext` loaded from `tls_cert` / `tls_key`

---

## 10. Packaging and Distribution

### `pyproject.toml` (key fields)

```
name = "redfish-client-sdk"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx",
    "pydantic>=2.0",
    "aiohttp",
]
```

### Installation

```
pip install redfish-client-sdk          # from PyPI (future)
pip install -e python/                  # from local source
```

### Import

```
import redfish_sdk
ctx = redfish_sdk.connect(host, credentials, mode)
```

---

## 11. Relationship to bmc-redfish-simulator

The Python SDK is the **Phase 1 delivery** and is validated against the
bmc-redfish-simulator before any C++ or Rust work begins.

The simulator provides:
- A Redfish endpoint at `http://127.0.0.1:8000`
- Session and Basic auth support
- EventService with subscription and SSE support
- LogService, TelemetryService, and UpdateService endpoints
- The AMD Platform mockup (`/home/hari/mockup/AMD_Platform_v3`)

All 12 sample clients are executable against the simulator using the
default `--host 127.0.0.1 --port 8000` arguments.

The SDK makes no assumptions that the simulator is present. It works
against the simulator because the simulator is Redfish-compliant —
not because of any special simulator integration.

---

## 12. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — Python architecture |
| 0.3 | 2026-03-07 | Copilot | §9 Event Listener expanded: context validation, latency logging, per-IP counter, buffered GET, MetricReport path, implementation notes |
| 0.4 | 2026-03-05 | Copilot | §5 Service Handles: `LogFilter` extended with `skip` field; `iter_entries_async()` added for nextLink auto-pagination; OData ordering rule documented |
