# Redfish Client SDK — Language-Independent Architecture

**Document ID:** RSDK-ARCH-001  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Architectural Goals](#2-architectural-goals)
3. [Component Model](#3-component-model)
4. [Component Responsibilities](#4-component-responsibilities)
5. [Layered Architecture](#5-layered-architecture)
6. [Client Context — The Central Pattern](#6-client-context--the-central-pattern)
7. [Architectural Decisions](#7-architectural-decisions)
8. [Component Interaction Flows](#8-component-interaction-flows)
9. [What Is Language-Independent vs Language-Specific](#9-what-is-language-independent-vs-language-specific)
10. [Change History](#10-change-history)

---

## 1. Purpose

This document defines the **language-independent architecture** of the Redfish
Client SDK. It establishes the component model, layering, key architectural
decisions, and interaction patterns that apply equally to the Python, C++, and
Rust implementations.

Each language-specific architecture document (RSDK-ARCH-002, RSDK-ARCH-003,
RSDK-ARCH-004) takes this document as its foundation and expresses it
idiomatically in the respective language.

---

## 2. Architectural Goals

The architecture shall support the following goals, derived directly from the
requirements (RSDK-REQ-001):

| Goal | Derived From |
|---|---|
| A single handle models a complete BMC connection | FR1.3, NFR3.1 |
| Discovery is optional — direct access never requires it | FR2, FR3.6 |
| All service APIs share the same established connection state | FR5–FR8 |
| Transport and auth are never exposed to the caller | NFR4, NFR6 |
| The same component model applies in all three languages | NFR1.5 |
| Multiple BMC connections are supported via multiple handles | NFR3.2 |
| Event Listener has its own independent lifecycle | FR5.3 |

---

## 3. Component Model

```
╔══════════════════════════════════════════════════════════════╗
║                    SDK PUBLIC SURFACE                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   connect()  ──────────────────────────────────────────►    ║
║                                              ClientContext   ║
║                                              (opaque handle) ║
║                                                    │         ║
║           ┌────────────────────────────────────────┤         ║
║           │               │              │         │         ║
║           ▼               ▼              ▼         ▼         ║
║     Discovery        Service         Direct    Event         ║
║     Component        Handles         Access    Listener      ║
║           │               │              │    (standalone)   ║
║           │     ┌─────────┼──────┬───────┘                  ║
║           │     ▼         ▼      ▼         ▼                 ║
║           │  Event      Log  Telemetry  Update               ║
║           │  Service  Service  Service  Service              ║
╠═══════════╪═══════════════════════════════════════════════════╣
║           │         PROTOCOL LAYER                           ║
║           │  RedfishResponse · TaskManager · MessageRegistry ║
╠═══════════╪═══════════════════════════════════════════════════╣
║           │         TRANSPORT LAYER                          ║
║           └► HTTP Engine · TLS · AuthManager · Session       ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 4. Component Responsibilities

Each component has exactly one responsibility. No component shall own
behaviour that belongs to another.

### SDK Entry Point

- Exposes the single `connect()` function that the caller invokes
- Validates connection parameters before attempting to contact the endpoint
- Delegates to the Transport Layer to establish the connection
- Delegates to the Auth Manager to perform authentication
- Constructs and returns a `ClientContext` handle on success
- This is the **only** public function in the SDK at the top level

---

### ClientContext (Opaque Handle)

- Represents one established connection to one Redfish endpoint
- Carries all state negotiated at connect time — auth, capabilities, config
- Is the access point for all subsequent SDK operations
- Has no business logic of its own — it is a state carrier and API gateway
- Its lifetime defines the lifetime of the connection
- Multiple independent instances can coexist in the same process

---

### Discovery Component

- Traverses the Redfish resource tree starting from ServiceRoot
- Supports three modes: Full, Partial (single node), Root-level only
- Populates the ClientContext with discovered service URIs
- Makes discovery results inspectable — caller can query what was found
- Does not gate any other SDK operation — it is always optional

---

### Service Handles

Four typed service handles, each scoped to one Redfish service:

| Handle | Redfish Service |
|---|---|
| EventService Handle | `/redfish/v1/EventService` |
| LogService Handle | `/redfish/v1/Systems/.../LogServices` |
| TelemetryService Handle | `/redfish/v1/TelemetryService` |
| UpdateService Handle | `/redfish/v1/UpdateService` |

Each handle:
- Is accessed via the ClientContext — not constructed directly by the caller
- Uses the ClientContext for all transport operations
- Exposes intent-driven APIs for its specific service domain
- Returns `RedfishResponse` for all operations

---

### Direct / Raw Access

- Exposes `get(uri)`, `post(uri, body)`, `patch(uri, body)`, `delete(uri)`
  directly on the ClientContext
- No interpretation of the response — returns raw `RedfishResponse`
- Used for OEM extensions, advanced scenarios, or when typed APIs are
  insufficient
- Uses the same Transport Layer as all other components

---

### Event Listener

- A standalone component with its own lifecycle — independent of the
  ClientContext
- Acts as an embedded HTTP(S) server that receives push event deliveries
  from the BMC
- Is wired to a ClientContext at start time but is not owned by it
- Caller registers event callbacks on the listener
- Delivers incoming events to registered callbacks
- Can be started and stopped independently of the client connection

---

### Protocol Layer

Three concerns, all internal to the SDK:

| Concern | Responsibility |
|---|---|
| **RedfishResponse** | Uniform response envelope for every SDK operation |
| **TaskManager** | Detects 202 responses, manages task polling, surfaces task handle |
| **MessageRegistry** | Fetches registries from BMC, decodes MessageId to human-readable form |

---

### Transport Layer

Entirely internal — never exposed to the caller. Four concerns:

| Concern | Responsibility |
|---|---|
| **HTTP Engine** | Executes HTTP requests and receives responses |
| **TLS** | Manages certificate validation or bypass per configuration |
| **AuthManager** | Executes the chosen auth flow at connect time |
| **Session** | Holds an active session token in memory if session mode is chosen |

---

## 5. Layered Architecture

The SDK is strictly layered. Each layer communicates only with the layer
directly below it. No layer skips a layer to talk to a lower one.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4 — Service APIs                                 │
│  EventService · LogService · Telemetry · UpdateService  │
│                                                         │
│  Provides: intent-driven Redfish service operations     │
│  Knows about: Protocol Layer                            │
│  Does NOT know about: Transport Layer internals         │
├─────────────────────────────────────────────────────────┤
│  Layer 3 — Protocol Layer                               │
│  RedfishResponse · TaskManager · MessageRegistry        │
│                                                         │
│  Provides: Redfish protocol normalization               │
│  Knows about: Transport Layer                           │
│  Does NOT know about: Service API specifics             │
├─────────────────────────────────────────────────────────┤
│  Layer 2 — Transport Layer                              │
│  HTTP Engine · TLS · AuthManager · Session              │
│                                                         │
│  Provides: raw HTTP execution over HTTPS                │
│  Knows about: network, TLS, credentials                 │
│  Does NOT know about: Redfish protocol or resources     │
├─────────────────────────────────────────────────────────┤
│  Layer 1 — Client Context                               │
│  Shared state carrier — threads through all layers      │
│                                                         │
│  Provides: connection state, auth state, capabilities   │
│  Carries: schema cache, discovery results, config       │
│  Contains: no business logic                            │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Client Context — The Central Pattern

### How It Is Created

The `ClientContext` is never constructed directly by the caller. It is
always returned by the SDK's `connect()` function after the connection
and authentication are fully established.

```
Caller invokes connect(host, credentials, auth_mode)
        │
        ▼
SDK validates parameters
        │
        ▼
Transport Layer opens HTTPS connection
        │
        ▼
AuthManager performs chosen auth flow
  ├── Session Mode:  POST to SessionService → stores token
  └── Stateless Mode: validates endpoint is reachable
        │
        ▼
SDK negotiates endpoint capabilities
  (short-form detection, OData version)
        │
        ▼
SDK constructs ClientContext with all negotiated state
        │
        ▼
Caller receives ClientContext handle
```

### What It Carries (Internal — Not Caller-Visible)

```
ClientContext
├── Endpoint:       host, port, base URI, TLS config, timeouts
├── Auth State:     mode (session/stateless), token or credentials
├── Capabilities:   short-form flag, OData version, available services
├── Schema Cache:   schemas fetched from BMC, accumulated over calls
└── Discovery Map:  service URIs found during discovery (if called)
```

### Two Auth Modes — Same Handle Shape

Both auth modes return the same `ClientContext` type. The caller
uses them identically. The auth difference is fully encapsulated.

| | Session Mode | Stateless Mode |
|---|---|---|
| **At connect** | POST to SessionService, token stored | Endpoint reachability verified |
| **Per call** | Token attached automatically | Credentials attached automatically |
| **Handle type** | `ClientContext` | `ClientContext` |
| **Caller experience** | Identical | Identical |

### Multiple BMC Connections

```
ctx_bmc1 = connect(host1, creds1, SESSION)
ctx_bmc2 = connect(host2, creds2, STATELESS)
ctx_bmc3 = connect(host3, creds3, SESSION)

# All three are independent — no shared state between them
# Concurrency between them is entirely the caller's responsibility
```

---

## 7. Architectural Decisions

### AD1 — Layered, Not Monolithic

**Decision:** The SDK is organized into four strict layers. Each layer
only communicates with the layer directly below it.

**Rationale:** Layering allows each concern to be tested independently,
replaced without affecting other layers, and understood in isolation.
It also makes the same architecture expressible in all three languages.

---

### AD2 — Discovery Is Optional, Never a Gate

**Decision:** All SDK operations — service handles, direct access,
raw APIs — are available immediately on the ClientContext. Discovery
does not need to be called first.

**Rationale:** Advanced callers who know their target URIs should not
be penalized with a discovery round-trip they do not need (FR2, FR3.6).

---

### AD3 — ClientContext Is the Caller-Held Opaque Handle

**Decision:** The SDK's `connect()` returns a `ClientContext` handle.
The caller holds this handle and passes it implicitly to all subsequent
operations. Its internals are never directly accessible to the caller.

**Rationale:** Eliminates redundant parameter passing across all SDK
calls. Encapsulates auth, connection, and negotiated state in one place.
Supports multiple simultaneous BMC connections cleanly.

---

### AD4 — Transport Is Fully Encapsulated

**Decision:** The Transport Layer — HTTP engine, TLS, auth tokens — is
never directly accessible to the caller. All HTTP is executed by the SDK.

**Rationale:** Protects callers from HTTP-level concerns. Ensures the SDK
can change its transport implementation without breaking callers (NFR4).

---

### AD5 — Uniform RedfishResponse for All Operations

**Decision:** Every SDK operation returns a `RedfishResponse`. The shape
is identical regardless of which service or layer produced it.

**Rationale:** Callers learn one response shape. Error handling is
consistent everywhere. The SDK makes no assumptions about how the caller
will use or handle the response (NFR4.2).

**RedfishResponse carries:**
- HTTP status code
- Success indicator
- Response headers
- Response body (raw JSON / structured map)
- Extended error information (Redfish `@Message.ExtendedInfo` if present)
- Task handle (present only if response was 202 Accepted)

---

### AD6 — Task Management Is Automatic

**Decision:** Any 202 Accepted response is automatically detected by the
Protocol Layer and a `RedfishTask` handle is attached to the
`RedfishResponse`. The caller does not need to detect 202 themselves.

**Rationale:** Task handling is a cross-cutting concern that appears
across Update, Log, and other services. Centralizing it eliminates
repetition and ensures consistent behaviour (FR4.1).

---

### AD7 — Event Listener Has an Independent Lifecycle

**Decision:** The `RedfishEventListener` is a standalone component,
not owned or managed by the `ClientContext`. It is wired to a context
at start time but runs on its own lifecycle.

**Rationale:** The listener is a server — it has a fundamentally
different lifecycle than a client connection. It must be startable
and stoppable independently. It may outlive or start before a client
connection (FR5.3, NFR3.4).

---

### AD8 — OEM Access Is Always Via Direct APIs

**Decision:** OEM-namespaced resources and actions are only accessible
via the Direct / Raw Access component. Service handles do not model
OEM extensions.

**Rationale:** OEM extensions break typed abstraction guarantees.
Forcing OEM access through raw APIs keeps service handles clean and
protects callers from vendor-specific fragility (FR3.7, NFR5.4).

---

## 8. Component Interaction Flows

### Flow 1 — Connect and Establish Context

```
Caller
  │── connect(host, creds, mode)
  │
  ▼
SDK Entry Point
  │── validate parameters
  │── Transport Layer: open HTTPS connection
  │── AuthManager: execute auth flow
  │── detect endpoint capabilities
  │── construct ClientContext
  │
  ▼
Caller receives ClientContext handle
```

---

### Flow 2 — Service API Call (e.g., Log Service)

```
Caller
  │── ctx.log_service.get_entries(filter)
  │
  ▼
LogService Handle
  │── resolve log service URI (from context or discovery map)
  │── build Redfish request
  │
  ▼
Protocol Layer
  │── attach OData headers
  │── pass to Transport Layer
  │
  ▼
Transport Layer
  │── attach auth (token or credentials from context)
  │── execute HTTPS GET
  │── receive response
  │
  ▼
Protocol Layer
  │── construct RedfishResponse
  │── detect 202? → attach RedfishTask handle
  │
  ▼
LogService Handle
  │── return RedfishResponse to caller
  │
  ▼
Caller receives RedfishResponse
```

---

### Flow 3 — Event Subscribe and Listen

```
Caller
  │── ctx.event_service.subscribe(destination, filters)
  │       → returns RedfishResponse with subscription ID
  │
  │── listener = RedfishEventListener(port)
  │── listener.on_event(my_callback)
  │── listener.start()
  │
  ▼
BMC pushes event to listener port
  │
  ▼
RedfishEventListener
  │── receives HTTP POST from BMC
  │── parses event payload
  │── resolves MessageId via MessageRegistry (using context)
  │── invokes registered callback with decoded event
  │
  ▼
Caller's callback receives event
```

---

### Flow 4 — Full Discovery

```
Caller
  │── ctx.discover()              # full discovery
  │── OR ctx.discover(node)       # partial — single node
  │── OR ctx.discover(root_only)  # root-level only
  │
  ▼
Discovery Component
  │── GET ServiceRoot via Transport Layer
  │── traverse linked resources per mode
  │── populate ClientContext discovery map with resolved URIs
  │── return discovery result to caller (inspectable)
  │
  ▼
Caller can inspect what was found
  ctx.discovery.has_service(EventService)
  ctx.discovery.has_service(TelemetryService)
  ctx.discovery.get_uri(Systems)
```

---

## 9. What Is Language-Independent vs Language-Specific

The following table defines the boundary between this document and the
three language-specific architecture documents.

| Concern | This Document | Language-Specific Arch |
|---|---|---|
| Component names and responsibilities | ✅ Defined here | Expressed idiomatically |
| Layer boundaries and rules | ✅ Defined here | Preserved in all languages |
| Architectural decisions (AD1–AD8) | ✅ Defined here | Applied in all languages |
| RedfishResponse shape | ✅ Defined here | Typed per language idiom |
| ClientContext pattern | ✅ Defined here | Implemented per language idiom |
| Flow interactions | ✅ Defined here | Verified in each language |
| Async / sync model | Contract defined here | Fulfilled per language (asyncio / coroutines / tokio) |
| Error surfacing | Contract defined here | Exceptions vs Result vs `?` |
| Package / module structure | — | Defined per language |
| Library dependencies | — | Defined per language |
| Build system | — | Defined per language |
| Memory management | — | GC vs RAII vs Ownership |
| Type system expression | — | Per language idiom |

---

## 10. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — language-independent architecture |
| 0.3 | 2026-03-07 | Copilot | FR5.1 extended subscription params; FR5.3 listener detail (context validation, latency logging, buffered events, per-IP counter); FR5.9 SubmitTestEvent; FR6.6 flat SEL format |
