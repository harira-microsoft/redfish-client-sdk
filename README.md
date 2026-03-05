# Redfish Client SDK

A multi-language SDK for building clients against any Redfish-compliant
endpoint — real BMC hardware (AMD, iLO, iDRAC) or a simulator.

---

## What is Redfish?

Redfish is the industry-standard REST API for managing servers and
infrastructure hardware. It is defined by the DMTF and supported by every
major hardware vendor. If you need to talk to a BMC (Baseboard Management
Controller) — to read sensors, subscribe to events, update firmware, or
pull logs — you are talking Redfish.

It runs over HTTPS. Resources are JSON. Operations are GET / POST / PATCH /
DELETE. That's it.

**The problem** is that the protocol has enough surface area (authentication,
session management, task polling, event subscriptions, schema discovery,
message registries) that writing a client from scratch takes days. This SDK
takes that away.

---

## What This SDK Does

```
connect(host, port, credentials) → handle

handle.get("/redfish/v1/Systems/1")
handle.event_service.subscribe(destination="http://my-server:9090")
handle.log_service.get_entries(log_uri)
handle.update_service.simple_update(image_uri)

listener = RedfishEventListener(port=9090)
listener.on_event(lambda event: print(event.message))
listener.start()
```

One function to connect. One handle for everything after. Events delivered
to your callback. Tasks polled automatically.

---

## Language Support

| Phase | Language | Status |
|---|---|---|
| 1 | Python | 🔧 In development |
| 2 | C++ | 📋 Designed |
| 3 | Rust | 📋 Designed |

Each language is a **first-class idiomatic implementation** — not a binding
over another language. Python first, because it is the fastest path to a
working client. C++ second, because BMC firmware teams live there. Rust
third, for teams that want compiler-enforced safety.

The C++ SDK also exposes an `extern "C"` surface, making it callable from
plain C — useful for RAS/CPER consumers at the platform layer.

---

## Project Layout

```
RedfishClientSDK/
│
├── docs/
│   ├── requirements.md                     ← What the SDK must do
│   ├── architecture/
│   │   ├── architecture-sdk.md             ← Language-independent design
│   │   ├── architecture-python.md          ← Python Phase 1
│   │   ├── architecture-cpp.md             ← C++ Phase 2
│   │   └── architecture-rust.md            ← Rust Phase 3
│   └── design/
│       ├── design-python.md                ← Python detailed design
│       ├── design-cpp.md                   ← C++ detailed design
│       └── design-rust.md                  ← Rust detailed design
│
├── python/                                 ← Python SDK (coming)
├── cpp/                                    ← C++ SDK (coming)
└── rust/                                   ← Rust SDK (coming)
```

Start with the docs. The requirements tell you *what*. The architecture
tells you *how it fits together*. The design tells you *exactly what to
implement*.

---

## Documentation

### Start Here

| Document | What it covers |
|---|---|
| [Requirements](docs/requirements.md) | Full feature and non-functional requirements |
| [SDK Architecture](docs/architecture/architecture-sdk.md) | Language-independent component model |

### By Language

| Language | Architecture | Design |
|---|---|---|
| Python | [architecture-python.md](docs/architecture/architecture-python.md) | [design-python.md](docs/design/design-python.md) |
| C++ | [architecture-cpp.md](docs/architecture/architecture-cpp.md) | [design-cpp.md](docs/design/design-cpp.md) |
| Rust | [architecture-rust.md](docs/architecture/architecture-rust.md) | [design-rust.md](docs/design/design-rust.md) |

---

## Key Concepts

### One Entry Point

Every SDK operation starts with `connect()`. It handles TLS, authentication,
and endpoint discovery. You get back an opaque handle. Pass nothing else
around.

### Session vs Stateless Auth

```
connect(..., auth_mode=SESSION)     # creates a Redfish session — preferred
connect(..., auth_mode=STATELESS)   # Basic Auth per request — simpler for tests
```

### Uniform Response

Every call returns a `RedfishResponse`:

```
response.success        → True / False
response.status_code    → 200, 201, 202, 404 ...
response.body           → parsed JSON
response.task           → populated if BMC returned 202 Accepted
response.extended_info  → decoded Redfish messages
```

404 is never an exception. It is a response with `success=False`. Your
code decides what to do with it.

### Tasks

Firmware updates and some config changes return `202 Accepted` with a
task URI. The SDK handles the polling:

```
response = handle.update_service.simple_update(image_uri)
if response.task:
    final = response.task.wait()   # blocks until done or timeout
```

### Event Listener

A standalone embedded HTTP server that receives push events from the BMC:

```
listener = RedfishEventListener(port=9090)
listener.on_event(my_callback)
listener.start()

# subscribe the BMC to send events to this listener
handle.event_service.subscribe(destination="http://my-host:9090")
```

### Discovery

The SDK can walk the service tree to find what's available:

```
result = handle.discovery.full()
result.has_service("TelemetryService")   # True / False
result.service_uri("EventService")       # /redfish/v1/EventService
```

---

## Testing Against the Simulator

All samples target the [bmc-redfish-simulator](https://github.com/your-org/bmc-redfish-simulator)
running locally on `127.0.0.1:8000`. No real hardware required to get
started.

```bash
# Start the simulator
cd /path/to/bmc-redfish-simulator
python main.py

# Run a sample (once Python SDK is available)
python python/samples/01_connect_discover.py --host 127.0.0.1 --port 8000
```

---

## Redfish Quick Reference

| Resource | Typical URI |
|---|---|
| Service root | `/redfish/v1` |
| Systems | `/redfish/v1/Systems` |
| Managers | `/redfish/v1/Managers` |
| Chassis | `/redfish/v1/Chassis` |
| Event Service | `/redfish/v1/EventService` |
| Log Services | `/redfish/v1/Systems/1/LogServices` |
| Telemetry | `/redfish/v1/TelemetryService` |
| Update Service | `/redfish/v1/UpdateService` |
| Sessions | `/redfish/v1/SessionService/Sessions` |
| Task Service | `/redfish/v1/TaskService/Tasks` |

All URIs are discovered at runtime — never hardcoded in the SDK.

---

## Contributing

Follow the engineering discipline this project was built on:

1. **Requirements first** — if it is not in `requirements.md`, discuss it
   before building it
2. **Design before code** — the design docs are the contract; update them
   if the implementation diverges
3. **Test against the simulator** — all samples must run against
   `bmc-redfish-simulator` before merge
4. **Match the API surface** — Python is the reference; C++ and Rust must
   mirror it

---

## Document IDs

| ID | Document |
|---|---|
| RSDK-REQ-001 | Requirements |
| RSDK-ARCH-001 | SDK Architecture |
| RSDK-ARCH-002 | Python Architecture |
| RSDK-ARCH-003 | C++ Architecture |
| RSDK-ARCH-004 | Rust Architecture |
| RSDK-DESIGN-001 | Python Design |
| RSDK-DESIGN-002 | C++ Design |
| RSDK-DESIGN-003 | Rust Design |
