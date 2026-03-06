# Quickstart — Redfish Client SDK

**Goal:** make a real Redfish request in under 5 minutes.

No hardware required. We use the DMTF Redfish Mockup Server as the target.

---

## 0. Prerequisites

| Item | Minimum | Notes |
|------|---------|-------|
| Python | 3.10+ | |
| Rust toolchain | 1.75+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| C++ build tools | g++ 9+, cmake 3.16+ | see `cpp/requirements.txt` for all platforms |
| Simulator | any Redfish server on port 8000 | install instructions below |

Pick **one language** to start. Python has the shortest path.

---

## 1. Start the Simulator

Every SDK sample defaults to `127.0.0.1:8000`. Install the DMTF mockup server:

```bash
pip install redfish-mockup-server
redfish-mockup-server --host 127.0.0.1 --port 8000
```

> **Important:** the mockup server speaks **plain HTTP** (no TLS).  
> Always pass `--no-tls` to samples when using it.

Leave the simulator running in one terminal and open a second for the SDK.

---

## 2. Python — first request

### Install

```bash
cd python/
pip install -e .
```

### Run sample 01

```bash
python samples/01_connect_discover.py --no-tls
```

Expected output:

```
Connecting to 127.0.0.1:8000 …
Redfish version : 1.6.0
Services found  :
  Systems          → /redfish/v1/Systems
  Chassis          → /redfish/v1/Chassis
  EventService     → /redfish/v1/EventService
  TelemetryService → /redfish/v1/TelemetryService
  ...
```

### Run the unit tests (no simulator needed)

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

All tests use `MockHttpClient` — no network, no simulator, no hardware required.

---

## 3. Rust — first request

### Build

```bash
cd rust/
cargo build --release
```

### Run sample 01

```bash
./target/release/01_connect_discover --host 127.0.0.1 --port 8000 --no-tls
```

### Run the test suite

```bash
cargo test
```

---

## 4. C++ — first request

### Install build dependencies

```bash
# Ubuntu / Debian
sudo apt install build-essential cmake libcurl4-openssl-dev \
                 libssl-dev nlohmann-json3-dev
# See cpp/requirements.txt for macOS, RHEL, Windows
```

### Build

```bash
cd cpp/
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

### Run sample 01

```bash
# argv: [host] [port]
./build/01_connect_discover 127.0.0.1 8000
```

*(C++ samples default `use_tls` to `false` for simulator use.)*

---

## 5. What just happened?

Sample 01 does four things in sequence:

```
connect(host, port, credentials)
  │
  ├─ 1. TCP connection + optional TLS handshake
  ├─ 2. Authentication (Session token or Basic Auth per request)
  ├─ 3. GET /redfish/v1  →  reads the Redfish service root
  └─ 4. Walks service keys  →  builds a service URI map
```

You get back a `ClientContext`. Everything else flows from that one handle:

```python
ctx = redfish_sdk.connect(host, port, credentials, auth_mode, config)

# Direct HTTP
response = ctx.get("/redfish/v1/Systems/1")
print(response.body["Model"])

# Service handles
ctx.event_service.subscribe(destination="http://my-listener:9090")
ctx.log_service.get_entries("/redfish/v1/Systems/1/LogServices/Log1")
ctx.update_service.push_firmware("/path/to/firmware.bin")
```

---

## 6. Learn by reading tests

`python/tests/test_quickstart.py` is a **tutorial disguised as a test file**.

Each test class covers one SDK concept with heavily commented examples:

| Class | Concept |
|---|---|
| `TestMockTransport` | How to test SDK code without a live BMC |
| `TestDirectRequests` | `ctx.get()`, `post()`, `patch()`, `delete()` |
| `TestResponseModel` | Reading `status_code`, `body`, `success`, `task` |
| `TestDiscovery` | Service root, full and partial discovery |
| `TestEventService` | Subscribe, list, delete subscriptions |
| `TestLogService` | List services, get entries, filter by severity |
| `TestConnectionConfig` | `use_tls` vs `verify_tls` — which one to use when |
| `TestErrorHandling` | When exceptions are raised vs when responses are returned |
| `TestFullContext` | Putting it all together |

Run and read them:

```bash
cd python/
pytest tests/test_quickstart.py -v -s
```

---

## 7. Common errors

| Error message | Cause | Fix |
|---|---|---|
| `SSL: WRONG_VERSION_NUMBER` | Simulator speaks HTTP, SDK sent HTTPS | Add `--no-tls` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Real BMC with self-signed cert | Add `--no-tls-verify` |
| `Cannot reach 127.0.0.1:8000` | Simulator not running | Start it first |
| `401 Unauthorized` | Wrong credentials | Check `--user` / `--password` |
| `ModuleNotFoundError: redfish_sdk` | SDK not installed | `pip install -e python/` |
| `cargo: command not found` | Rust not installed | `rustup` — see above |

---

## 8. What to read next

| Goal | Document |
|---|---|
| Full API reference (Python) | [python/docs/api-guide.md](../python/docs/api-guide.md) |
| Full API reference (C++) | [cpp/docs/api-guide.md](../cpp/docs/api-guide.md) |
| All 15 samples explained | [python/samples/README.md](../python/samples/README.md) |
| Architecture overview | [docs/architecture/architecture-sdk.md](architecture/architecture-sdk.md) |
| Performance comparison | [docs/performance.md](performance.md) |
| Contributing | [CONTRIBUTING.md](../CONTRIBUTING.md) |
