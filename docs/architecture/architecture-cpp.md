# Redfish Client SDK — C++ Architecture

**Document ID:** RSDK-ARCH-003  
**Version:** 0.1 (Draft)  
**Status:** Locked  
**Date:** March 4, 2026  
**Author:** Hari  
**Requirement Ref:** RSDK-REQ-001  
**Base Architecture:** RSDK-ARCH-001  
**API Reference:** RSDK-ARCH-002 (Python)  

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [C++-Specific Architectural Goals](#2-c-specific-architectural-goals)
3. [Technology Choices](#3-technology-choices)
4. [Project and Directory Structure](#4-project-and-directory-structure)
5. [Component Expression in C++](#5-component-expression-in-c)
6. [Async and Sync Model in C++](#6-async-and-sync-model-in-c)
7. [ClientContext in C++](#7-clientcontext-in-c)
8. [RedfishResponse in C++](#8-redfishresponse-in-c)
9. [Event Listener in C++](#9-event-listener-in-c)
10. [extern "C" Surface](#10-extern-c-surface)
11. [Build System](#11-build-system)
12. [Change History](#12-change-history)

---

## 1. Purpose

This document defines the C++ architecture for Phase 2 of the Redfish
Client SDK. It takes the language-independent architecture (RSDK-ARCH-001)
as its foundation, uses the Python Phase 1 API (RSDK-ARCH-002) as the
design reference, and expresses every component and decision idiomatically
in C++20.

The C++ implementation is the **Phase 2 delivery** — built after the Python
SDK is validated. The API surface mirrors Python's validated design.

---

## 2. C++-Specific Architectural Goals

| Goal | Rationale |
|---|---|
| C++20 as the language standard | Coroutines, concepts, `std::span`, `std::expected` — all needed |
| RAII for all resource management | No manual lifetime management for callers |
| Header-only public API surface | Callers include headers only — no ABI fragility |
| Zero-cost abstractions where possible | C++ SDK targets BMC firmware teams — performance matters |
| Clean `extern "C"` surface | Enables future Rust FFI without SDK changes |
| CMake as the build system | Industry standard for C++ — widely understood by BMC teams |

---

## 3. Technology Choices

### Core Dependencies

| Concern | Library | Reason |
|---|---|---|
| HTTP transport (sync) | `libcurl` | Mature, universally available, excellent TLS support |
| HTTP transport (async) | `Boost.Beast` or `cpp-httplib` (async) | C++ async HTTP over ASIO |
| Async runtime | `Boost.Asio` | Pairs with Beast; well-established async I/O |
| JSON parsing | `nlohmann/json` | Header-only, clean API, widely used in C++ |
| C++20 coroutines | stdlib (`co_await`, `co_return`) | No external library — part of C++20 |
| TLS | OpenSSL or mbedTLS | OpenSSL for servers; mbedTLS for embedded BMC targets |
| Event Listener server | `Boost.Beast` HTTP server | Shares the async stack already in use |

### Development / Build Dependencies

| Concern | Library | Reason |
|---|---|---|
| Build system | CMake 3.20+ | Industry standard |
| Dependency management | `vcpkg` or `Conan` | Modern C++ package management |
| Unit testing | GoogleTest | Standard for C++ unit tests |
| Static analysis | `clang-tidy` | Enforce code quality |

---

## 4. Project and Directory Structure

```
RedfishClientSDK/
└── cpp/
    ├── CMakeLists.txt                  # Root CMake — builds lib + samples + tests
    ├── vcpkg.json                      # Dependency manifest
    │
    ├── include/
    │   └── redfish/                    # Public headers — all callers include from here
    │       ├── redfish.hpp             # Single-include convenience header
    │       ├── client.hpp              # connect() function declaration
    │       ├── context.hpp             # ClientContext — public interface only
    │       ├── response.hpp            # RedfishResponse type
    │       ├── task.hpp                # RedfishTask handle
    │       ├── discovery.hpp           # Discovery API
    │       ├── event_listener.hpp      # RedfishEventListener
    │       ├── services/
    │       │   ├── event_service.hpp
    │       │   ├── log_service.hpp
    │       │   ├── telemetry_service.hpp
    │       │   └── update_service.hpp
    │       └── redfish_c_api.h         # extern "C" surface for FFI
    │
    ├── src/                            # Private implementation — not installed
    │   ├── client.cpp
    │   ├── context.cpp
    │   ├── discovery/
    │   │   └── discovery.cpp
    │   ├── services/
    │   │   ├── event_service.cpp
    │   │   ├── log_service.cpp
    │   │   ├── telemetry_service.cpp
    │   │   └── update_service.cpp
    │   ├── events/
    │   │   └── listener.cpp
    │   ├── protocol/
    │   │   ├── response.cpp
    │   │   ├── task.cpp
    │   │   └── registry.cpp
    │   ├── transport/
    │   │   ├── http_client.cpp
    │   │   ├── auth.cpp
    │   │   └── tls.cpp
    │   └── c_api/
    │       └── redfish_c_api.cpp       # extern "C" wrapper implementation
    │
    ├── samples/
    │   ├── CMakeLists.txt
    │   ├── 01_connect_discover.cpp
    │   ├── 02_partial_discover.cpp
    │   ├── 03_get_resources.cpp
    │   ├── 04_direct_api.cpp
    │   ├── 05_event_subscribe.cpp
    │   ├── 06_event_listener.cpp
    │   ├── 07_event_monitor.cpp
    │   ├── 08_log_service.cpp
    │   ├── 09_telemetry.cpp
    │   ├── 10_update_service.cpp
    │   ├── 11_task_polling.cpp
    │   └── 12_session_vs_stateless.cpp
    │
    └── tests/
        ├── CMakeLists.txt
        ├── unit/
        └── integration/
```

---

## 5. Component Expression in C++

### SDK Entry Point → `include/redfish/client.hpp`

A free function `connect()` in the `redfish` namespace. Not a class.
Two overloads:

- Sync: `ClientContext connect(params)` — blocks, returns context by value
- Async: `std::future<ClientContext> connect_async(params)` or
  coroutine returning `ClientContext`

The caller never constructs a `ClientContext` — they call `redfish::connect()`.

---

### ClientContext → `include/redfish/context.hpp`

An opaque class using the **Pimpl (Pointer to Implementation)** idiom.
The public header exposes only the interface. All data members live in
the private implementation class hidden in `src/context.cpp`.

This provides:
- Stable ABI — callers are not broken by internal changes
- Clean separation between interface and implementation
- Naturally opaque — callers cannot access internals even if they wanted to

Ownership model: `ClientContext` is **move-only**. It cannot be copied.
Moving it transfers ownership of the connection. This enforces the
one-connection-per-context semantic cleanly.

RAII: The `ClientContext` destructor closes the session and releases
the connection automatically. Callers never need to explicitly close.

---

### Discovery → `include/redfish/discovery.hpp`

Accessed via `ctx.discovery()`. Returns a `Discovery` object with three
methods:

- `full()` / `full_async()`
- `partial(service_name)` / `partial_async(service_name)`
- `root()` / `root_async()`

Each returns a `DiscoveryResult` — an inspectable value type.

---

### Service Handles → `include/redfish/services/`

Each service handle is a lightweight proxy class. They are accessed via
methods on `ClientContext`:

- `ctx.event_service()` → `EventServiceHandle`
- `ctx.log_service()` → `LogServiceHandle`
- `ctx.telemetry_service()` → `TelemetryServiceHandle`
- `ctx.update_service()` → `UpdateServiceHandle`

Handles do not own any connection state — they borrow it from the context.
They are cheap to create and do not need to be stored by the caller.

All methods on handles exist in sync and async variants.

---

### Protocol Layer → `src/protocol/`

Internal only. Three units:

- `response.cpp` — `RedfishResponse` as a value type (struct)
- `task.cpp` — `RedfishTask` handle, `TaskManager` using async polling
- `registry.cpp` — `MessageRegistry` that fetches and caches from BMC

---

### Transport Layer → `src/transport/`

Internal only. Three units:

- `http_client.cpp` — wraps `libcurl` (sync) and `Boost.Beast` (async)
  behind a uniform internal interface
- `auth.cpp` — implements session and stateless auth flows
- `tls.cpp` — constructs OpenSSL/mbedTLS context from connection config

---

### Event Listener → `include/redfish/event_listener.hpp`

A standalone class `RedfishEventListener`. Like Python, it has its own
lifecycle independent of `ClientContext`.

Built on `Boost.Beast` HTTP server running on its own `asio::io_context`.
The listener's `io_context` runs on a dedicated thread owned by the listener.
This is the **one exception** to NFR3.4 — the listener inherently requires
its own I/O thread.

---

## 6. Async and Sync Model in C++

### The Pattern

The async implementation uses **C++20 coroutines** with `co_await`.
The sync implementation drives the async coroutine to completion using
`Boost.Asio::io_context::run()` on a temporary context.

```
Async (primary):   co_await ctx.get_async(uri)  →  RedfishResponse
Sync (wrapper):    ctx.get(uri)                 →  RedfishResponse
```

As in Python, business logic lives **once** in the async implementation.
The sync wrapper does not duplicate logic — it drives the async path.

### Naming Convention

Mirrors the Python convention for consistency:

| Async variant | Sync variant |
|---|---|
| `get_async(uri)` → awaitable | `get(uri)` → blocking |
| `subscribe_async(...)` → awaitable | `subscribe(...)` → blocking |
| `connect_async(...)` → awaitable | `connect(...)` → blocking |

---

## 7. ClientContext in C++

### Pimpl Pattern

```
// Public header — included by callers
class ClientContext {
public:
    // Service access
    EventServiceHandle  event_service();
    LogServiceHandle    log_service();
    TelemetryServiceHandle telemetry_service();
    UpdateServiceHandle update_service();
    Discovery           discovery();

    // Direct / raw access
    RedfishResponse     get(std::string_view uri);
    RedfishResponse     post(std::string_view uri, nlohmann::json body);
    RedfishResponse     patch(std::string_view uri, nlohmann::json body);
    RedfishResponse     del(std::string_view uri);

    // Async variants
    std::future<RedfishResponse> get_async(std::string_view uri);
    // ... etc

    bool is_connected() const;

    // Move-only
    ClientContext(ClientContext&&) noexcept;
    ClientContext& operator=(ClientContext&&) noexcept;
    ClientContext(const ClientContext&) = delete;
    ClientContext& operator=(const ClientContext&) = delete;

    ~ClientContext();  // RAII — closes session, releases transport

private:
    struct Impl;                    // Forward declared only
    std::unique_ptr<Impl> _impl;    // All state lives here
};
```

### Impl (Private — `src/context.cpp`)

All data members live here. Never visible to callers:

| Member | Contents |
|---|---|
| `http_client` | The internal HTTP client instance |
| `auth_state` | Current auth mode and session token or credentials |
| `capabilities` | Negotiated endpoint capabilities |
| `schema_cache` | `std::unordered_map<std::string, nlohmann::json>` |
| `discovery_map` | `std::unordered_map<std::string, std::string>` |
| `config` | Timeouts, TLS settings, base URL |

---

## 8. RedfishResponse in C++

A value type — copyable and movable. No heap allocation for the struct
itself. Expressed as a plain struct in the public header.

### Fields

| Field | Type | Description |
|---|---|---|
| `status_code` | `int` | HTTP status code |
| `success` | `bool` | True if status_code is 2xx |
| `headers` | `std::unordered_map<std::string, std::string>` | Response headers |
| `body` | `nlohmann::json` | Parsed JSON body |
| `extended_info` | `std::vector<RedfishMessage>` | Extended error info |
| `task` | `std::optional<RedfishTask>` | Present only on 202 responses |
| `raw` | `std::string` | Raw response body |

### RedfishMessage (nested struct)

| Field | Type | Description |
|---|---|---|
| `message_id` | `std::string` | DMTF MessageId |
| `message` | `std::string` | Human-readable text |
| `severity` | `std::string` | OK / Warning / Critical |
| `resolution` | `std::optional<std::string>` | Resolution if provided |

---

## 9. Event Listener in C++

### Lifecycle

```cpp
auto listener = RedfishEventListener{9090};
listener.use_context(ctx);
listener.on_event([](const RedfishEvent& event) {
    // handle event
});
listener.start();   // non-blocking — starts internal io_context thread
// ...
listener.stop();    // stops internal thread gracefully
```

RAII: `RedfishEventListener` destructor calls `stop()` automatically.

---

## 10. extern "C" Surface

A thin C-compatible wrapper over the C++ API. Lives in
`include/redfish/redfish_c_api.h` and `src/c_api/redfish_c_api.cpp`.

### Purpose

- Enables Rust FFI bindings in Phase 3 without modifying the C++ SDK
- Enables any language with C FFI capability to bind to the SDK
- Contains **no business logic** — it is a pure translation layer

### Design Principles

- All handles are opaque pointers (`void*`)
- All strings are `const char*`
- All complex types (JSON body) are serialized strings
- All return values are either primitive types or opaque handles
- Memory ownership is explicitly documented per function

---

## 11. Build System

### CMake Structure

```
cpp/CMakeLists.txt              # Defines: redfish_sdk (lib), options, installs
cpp/src/CMakeLists.txt          # Internal sources
cpp/samples/CMakeLists.txt      # Sample executables
cpp/tests/CMakeLists.txt        # Test executables
```

### Build Targets

| Target | Output |
|---|---|
| `redfish_sdk` | Static library `libredfish_sdk.a` |
| `redfish_sdk_shared` | Shared library `libredfish_sdk.so` |
| `redfish_samples` | All sample executables |
| `redfish_tests` | All test executables |

### Build Command

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

---

## 12. Change History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-03-04 | Hari | Initial draft — C++ architecture |
