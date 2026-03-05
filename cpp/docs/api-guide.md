# Redfish SDK — C++ API Guide

Practical reference for the C++ SDK. Every public interface with short
examples. No theory — just what you need to write a working client.

---

## Build Prerequisites

| Dependency | Minimum version | Install (Ubuntu / Debian) |
|---|---|---|
| g++ | 9+ (C++17) | `sudo apt install build-essential` |
| CMake | 3.16+ | `sudo apt install cmake` |
| libcurl | any | `sudo apt install libcurl4-openssl-dev` |
| OpenSSL | any | `sudo apt install libssl-dev` |
| nlohmann-json | 3.2+ | `sudo apt install nlohmann-json3-dev` |

---

## Build

```bash
cd cpp/
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

Debug build:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
```

Binaries land in `build/`:

```
build/01_connect_discover
build/05_event_subscribe
build/08_log_service
build/09_telemetry
...
```

---

## Quick Start

```cpp
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>

int main() {
    redfish::Credentials creds{"admin", "password"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;   // plain HTTP for simulator / dev

    try {
        auto ctx = redfish::connect(
            "127.0.0.1", 8000,
            creds,
            redfish::AuthMode::SESSION,
            config
        );

        auto r = ctx->get("/redfish/v1/Systems");
        std::cout << r.body.dump(2) << "\n";

        // ctx destructor calls logout() automatically

    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
        return 1;
    }
}
```

---

## redfish::connect()

The only SDK entry point. Returns a `std::unique_ptr<ClientContext>`.

```cpp
std::unique_ptr<ClientContext> ctx = redfish::connect(
    "127.0.0.1",              // host
    8000,                     // port
    creds,                    // Credentials{username, password}
    redfish::AuthMode::SESSION,  // or AuthMode::STATELESS
    config                    // ConnectionConfig — optional, all defaults shown below
);
```

### ConnectionConfig defaults

```cpp
redfish::ConnectionConfig config;
config.verify_tls             = true;    // false → accept self-signed / plain HTTP
config.tls_ca_cert            = "";      // path to custom CA cert file (PEM)
config.tls_client_cert        = "";      // mTLS client cert path
config.tls_client_key         = "";      // mTLS client key path
config.connect_timeout_sec    = 10;
config.request_timeout_sec    = 30;
config.task_poll_interval_sec = 5;
config.task_timeout_sec       = 300;
config.allow_session_fallback = false;   // true → try SESSION, fall back to STATELESS
```

### Exceptions thrown by connect()

| Exception | When |
|---|---|
| `redfish::RedfishConnectionError` | Host unreachable or refused |
| `redfish::RedfishTLSError` | TLS handshake / cert validation failed |
| `redfish::RedfishAuthError` | Wrong credentials (401 / 403) |
| `redfish::RedfishProtocolError` | Server not a Redfish endpoint |

---

## ClientContext

The handle returned by `connect()`. Never construct directly.

```cpp
auto ctx = redfish::connect(...);  // unique_ptr<ClientContext>

// Introspection
const redfish::DiscoveryResult&      disc = ctx->discovery();
const redfish::EndpointCapabilities& cap  = ctx->capabilities();
const redfish::AuthState&            auth = ctx->auth_state();

// Service handles (references — owned by ctx)
redfish::EventServiceHandle&     ev  = ctx->events();
redfish::LogServiceHandle&       log = ctx->logs();
redfish::TelemetryServiceHandle& tel = ctx->telemetry();
redfish::UpdateServiceHandle&    upd = ctx->update();

// Explicit logout (also called automatically by destructor)
ctx->logout();
```

`ClientContext` is non-copyable. Pass a raw pointer or reference when you
need to share the handle across functions.

---

## RedfishResponse

Every SDK call returns a `RedfishResponse`.

```cpp
redfish::RedfishResponse r = ctx->get("/redfish/v1/Systems/1");

r.success         // true if HTTP 2xx
r.status_code     // 200, 201, 202, 404 ...
r.body            // nlohmann::json — null if no body
r.headers         // std::map<std::string,std::string> — lowercase keys
r.extended_info   // std::vector<RedfishMessage>
r.raw             // raw body string

// Convenience accessors
r.location()      // value of Location header, or ""
r.x_auth_token()  // value of X-Auth-Token header, or ""
r.is_error()      // !success
```

**404 is never an exception.** It returns a response with `success=false`.

```cpp
auto r = ctx->get("/redfish/v1/Systems/does-not-exist");
if (!r.success)
    std::cerr << "Not found: " << r.status_code << "\n";
```

### RedfishMessage

```cpp
struct RedfishMessage {
    std::string message_id;
    std::string message;
    std::string severity;                    // "OK", "Warning", "Critical"
    std::optional<std::string> resolution;
    std::vector<std::string>   message_args;
};
```

---

## Direct HTTP Access

Use these to call any URI directly — OEM resources, custom paths, anything
not covered by a service handle.

```cpp
auto r = ctx->get("/redfish/v1/Systems");
auto r = ctx->post("/redfish/v1/Systems/1/Actions/ComputerSystem.Reset",
                   {{"ResetType", "GracefulRestart"}});
auto r = ctx->patch("/redfish/v1/Systems/1",
                    {{"AssetTag", "rack-42"}});
auto r = ctx->delete_("/redfish/v1/SessionService/Sessions/abc123");
```

`post` and `patch` accept an `nlohmann::json` body. Pass `nullptr` or
omit the argument to send no body.

---

## Discovery

`ctx->discovery()` returns the `DiscoveryResult` built during `connect()`.
No extra network call required.

```cpp
const auto& disc = ctx->discovery();

disc.redfish_version             // e.g. "1.6.0"
disc.service_map                 // std::map<std::string,std::string>
                                 //   "Systems" → "/redfish/v1/Systems"
                                 //   "EventService" → "/redfish/v1/EventService"

disc.capabilities.has_systems         // bool
disc.capabilities.has_managers        // bool
disc.capabilities.has_chassis         // bool
disc.capabilities.has_event_service   // bool
disc.capabilities.has_telemetry       // bool
disc.capabilities.has_update_service  // bool
disc.capabilities.has_log_service     // bool
disc.capabilities.has_session_service // bool
disc.capabilities.has_account_service // bool
disc.capabilities.has_task_service    // bool
```

Iterate the service map:

```cpp
for (const auto& [name, uri] : ctx->discovery().service_map)
    std::cout << name << " → " << uri << "\n";
```

---

## EventService

```cpp
auto& ev = ctx->events();

// Service capabilities
auto r = ev.get_service_info();

// Subscribe — BMC will POST events to your listener URL
auto r = ev.subscribe(
    "http://my-host:9090/events",          // destination (required)
    {"Alert", "ResourceUpdated"},          // event_types   (optional)
    {"OpenBMC", "Base"},                   // registry_prefixes (optional)
    {},                                    // message_ids   (optional)
    "my-context-string",                   // context       (optional)
    "Redfish",                             // protocol      (default "Redfish")
    "RedfishEvent"                         // subscription_type (default "RedfishEvent")
);

std::string sub_uri;
if (r.success) {
    sub_uri = r.location();               // prefer Location header
    if (sub_uri.empty())
        sub_uri = r.body.value("@odata.id", "");
}

// List, inspect, delete
auto r = ev.list_subscriptions();
auto r = ev.get_subscription("/redfish/v1/EventService/Subscriptions/1");
auto r = ev.delete_subscription("/redfish/v1/EventService/Subscriptions/1");

// Submit a test event (simulator / test use)
auto r = ev.submit_test_event();

// With a custom payload
nlohmann::json payload = {
    {"EventType",    "Alert"},
    {"MessageId",    "Base.1.8.GeneralError"},
    {"Message",      "Test message from C++ SDK"},
    {"Severity",     "OK"},
    {"OriginOfCondition", {{"@odata.id", "/redfish/v1/Systems/1"}}},
    {"MessageArgs",  nlohmann::json::array()}
};
auto r = ev.submit_test_event(payload);
```

---

## LogService

```cpp
auto& log = ctx->logs();

// List available log services under Systems/1 and Managers
auto r = log.list_services();

// List entries from a specific log service
auto r = log.list_entries("/redfish/v1/Systems/1/LogServices/EventLog");

// With filters
auto r = log.list_entries(
    "/redfish/v1/Systems/1/LogServices/EventLog",
    50,               // top — maximum entries (std::optional<int>)
    "Severity eq 'Critical'"   // OData filter string
);

// Single entry
auto r = log.get_entry("/redfish/v1/Systems/1/LogServices/EventLog/Entries/1");

// Clear a log
auto r = log.clear_log("/redfish/v1/Systems/1/LogServices/EventLog");
```

---

## TelemetryService

```cpp
auto& tel = ctx->telemetry();

// Service info
auto r = tel.get_service_info();

// Metric Report Definitions — what the BMC can report
auto r = tel.list_report_definitions();
auto r = tel.list_metric_definitions();

// Metric Reports — actual data
auto r = tel.list_metric_reports();
auto r = tel.get_metric_report("/redfish/v1/TelemetryService/MetricReports/All");

// Access metric values from the report body
if (r.success && r.body.contains("MetricValues")) {
    for (const auto& mv : r.body["MetricValues"]) {
        std::cout << mv.value("MetricId", "") << ": "
                  << mv.value("MetricValue", "") << "\n";
    }
}
```

---

## UpdateService

```cpp
auto& upd = ctx->update();

// Service info
auto r = upd.get_service_info();

// Firmware inventory
auto r = upd.list_firmware_inventory();
auto r = upd.get_firmware_component("/redfish/v1/UpdateService/FirmwareInventory/BMC");

// Initiate an update — returns 202 with a task if the BMC accepts it
auto r = upd.simple_update(
    "http://my-server/firmware.bin",                // image_uri (required)
    "HTTP",                                         // transfer_protocol (default "HTTP")
    {"/redfish/v1/UpdateService/FirmwareInventory/BMC"}  // targets (optional)
);

if (r.status_code == 202) {
    // Extract the task URI from the Location header
    std::string task_uri = r.location();
    std::cout << "Task started: " << task_uri << "\n";
}
```

---

## Tasks

When a BMC operation returns `202 Accepted`, use `poll_task()` to wait for
completion.

```cpp
#include "redfish_sdk/protocol/task.hpp"

// r is the 202 response from simple_update(), a POST action, etc.
if (r.status_code == 202) {
    std::string task_uri = r.location();

    // Poll with defaults from ConnectionConfig
    auto final_r = redfish::poll_task(
        http_client,              // HttpClient& — internal, accessed via ctx
        auth_state,               // AuthState&  — internal, accessed via ctx
        task_uri,
        config.task_poll_interval_sec,   // 5 seconds
        config.task_timeout_sec          // 300 seconds
    );

    std::cout << "Final state: "
              << final_r.body.value("TaskState", "unknown") << "\n";
}
```

### TaskState values

```cpp
enum class TaskState {
    New, Starting, Running, Suspended, Interrupted,
    Pending, Stopping, Completed, Killed, Exception, Service
};
```

Terminal states: `Completed`, `Killed`, `Exception`

### Progress callback

```cpp
auto final_r = redfish::poll_task(
    http, auth, task_uri,
    poll_interval_sec, timeout_sec,
    [](const redfish::RedfishTask& task) {
        std::cout << "State: "
                  << static_cast<int>(task.state)
                  << "  " << task.percent_complete << "%\n";
    }
);
```

---

## Error Handling

All exceptions derive from `redfish::RedfishError` which derives from
`std::runtime_error`.

```cpp
#include "redfish_sdk/errors.hpp"

try {
    auto ctx = redfish::connect(
        "bmc.local", 443,
        redfish::Credentials{"admin", "wrong"},
        redfish::AuthMode::SESSION
    );
} catch (const redfish::RedfishAuthError& e) {
    std::cerr << "Bad credentials: " << e.what() << "\n";
} catch (const redfish::RedfishConnectionError& e) {
    std::cerr << "Cannot reach host: " << e.what() << "\n";
} catch (const redfish::RedfishTLSError& e) {
    std::cerr << "TLS error: " << e.what() << "\n";
} catch (const redfish::RedfishProtocolError& e) {
    std::cerr << "Not a Redfish endpoint: " << e.what() << "\n";
} catch (const redfish::RedfishError& e) {
    std::cerr << "SDK error: " << e.what() << "\n";
}
```

```cpp
try {
    auto final_r = redfish::poll_task(...);
} catch (const redfish::RedfishTimeoutError& e) {
    std::cerr << "Task timed out: " << e.what() << "\n";
} catch (const redfish::RedfishTaskError& e) {
    std::cerr << "Task failed: " << e.what() << "\n";
}
```

### Exception hierarchy

```
std::runtime_error
  └── redfish::RedfishError
        ├── redfish::RedfishConnectionError
        ├── redfish::RedfishAuthError
        ├── redfish::RedfishTLSError
        ├── redfish::RedfishProtocolError
        ├── redfish::RedfishTimeoutError
        └── redfish::RedfishTaskError
```

---

## Auth Modes

```cpp
// SESSION (preferred) — POST to SessionService, use X-Auth-Token
auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION);

// STATELESS — Basic Auth on every request, no session created
auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::STATELESS);

// SESSION with fallback to STATELESS if session creation fails
redfish::ConnectionConfig config;
config.allow_session_fallback = true;
auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION, config);

// Check which mode is active after connect
if (ctx->auth_state().mode == redfish::AuthMode::SESSION)
    std::cout << "Using session: " << ctx->auth_state().token << "\n";
```

---

## Typical Patterns

### Connect, work, close

```cpp
try {
    auto ctx = redfish::connect("127.0.0.1", 8000, creds,
                                redfish::AuthMode::SESSION, config);

    auto r = ctx->get("/redfish/v1/Systems");
    if (r.success)
        std::cout << r.body.dump(2) << "\n";

    // ctx goes out of scope → destructor calls logout()
} catch (const redfish::RedfishError& e) {
    std::cerr << e.what() << "\n";
}
```

### Multiple BMC connections

```cpp
auto ctx1 = redfish::connect("bmc-1.local", 443, creds1,
                              redfish::AuthMode::SESSION);
auto ctx2 = redfish::connect("bmc-2.local", 443, creds2,
                              redfish::AuthMode::SESSION);

auto r1 = ctx1->get("/redfish/v1/Systems");
auto r2 = ctx2->get("/redfish/v1/Systems");
// Each context is independent — no shared state
```

### Check capabilities before using a service

```cpp
auto ctx = redfish::connect(...);
const auto& cap = ctx->capabilities();

if (cap.has_event_service) {
    auto r = ctx->events().get_service_info();
    std::cout << r.body.dump(2) << "\n";
}

if (cap.has_telemetry) {
    auto r = ctx->telemetry().list_metric_reports();
    // ...
}
```

### Iterate a Redfish collection

```cpp
auto r = ctx->get("/redfish/v1/Systems");
if (r.success && r.body.contains("Members")) {
    for (const auto& member : r.body["Members"]) {
        std::string uri = member.value("@odata.id", "");
        auto detail = ctx->get(uri);
        std::cout << detail.body.value("Id", "") << "\n";
    }
}
```

---

## Running the Samples

All samples target the simulator at `127.0.0.1:8000`.

```bash
# Start the simulator
cd /path/to/bmc-redfish-simulator
python main.py

# Build the samples
cd cpp/
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel

# Run any sample
./build/01_connect_discover
./build/05_event_subscribe
./build/09_telemetry

# Override host/port
./build/01_connect_discover bmc.local 443
```

### Sample index

| Sample | What it shows |
|---|---|
| `01_connect_discover` | `connect()`, `discovery()`, `capabilities()` |
| `02_partial_discover` | Lightweight discovery, service map iteration |
| `03_get_resources` | Walk Systems / Managers / Chassis collections |
| `04_direct_api` | `get` / `post` / `patch` / `delete_` |
| `05_event_subscribe` | `subscribe`, `submit_test_event`, `delete_subscription` |
| `08_log_service` | `list_services`, `list_entries`, `clear_log` |
| `09_telemetry` | `get_service_info`, `list_metric_reports` |
| `12_session_vs_stateless` | Both auth modes, `allow_session_fallback` |

---

## Header Reference

| Header | What it provides |
|---|---|
| `redfish_sdk/client.hpp` | `redfish::connect()` |
| `redfish_sdk/context.hpp` | `ClientContext` |
| `redfish_sdk/errors.hpp` | Full exception hierarchy |
| `redfish_sdk/models/redfish_types.hpp` | `AuthMode`, `Credentials`, `ConnectionConfig`, `EndpointCapabilities`, `AuthState`, `TLSConfig`, `TimeoutConfig` |
| `redfish_sdk/protocol/response.hpp` | `RedfishResponse`, `RedfishMessage`, `build_response()` |
| `redfish_sdk/protocol/task.hpp` | `RedfishTask`, `TaskState`, `poll_task()` |
| `redfish_sdk/discovery/discovery.hpp` | `Discovery`, `DiscoveryResult` |
| `redfish_sdk/services/event_service.hpp` | `EventServiceHandle` |
| `redfish_sdk/services/log_service.hpp` | `LogServiceHandle` |
| `redfish_sdk/services/telemetry_service.hpp` | `TelemetryServiceHandle` |
| `redfish_sdk/services/update_service.hpp` | `UpdateServiceHandle` |
| `redfish_sdk/transport/http_client.hpp` | `HttpClient` (internal — rarely needed directly) |
| `redfish_sdk/transport/auth.hpp` | `AuthManager` (internal) |
| `redfish_sdk/transport/tls.hpp` | `build_tls_config()` (internal) |
