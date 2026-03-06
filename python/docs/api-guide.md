# Redfish SDK — Python API Guide

This is the practical reference for using the Python SDK. It covers every
public interface with short examples. No theory — just what you need to
write a working client.

---

## Installation

```bash
cd python/
pip install -e .
```

---

## Quick Start

```python
import redfish_sdk
from redfish_sdk import AuthMode, Credentials, ConnectionConfig

ctx = redfish_sdk.connect(
    host="127.0.0.1",
    port=8000,
    credentials=Credentials(username="admin", password="password"),
    auth_mode=AuthMode.SESSION,
)

response = ctx.get("/redfish/v1/Systems")
print(response.body)

ctx.close()
```

---

## connect()

The only SDK entry point. Returns a `ClientContext` handle.

```python
# Sync
ctx = redfish_sdk.connect(
    host        = "127.0.0.1",
    port        = 8000,
    credentials = Credentials(username="admin", password="password"),
    auth_mode   = AuthMode.SESSION,      # or AuthMode.STATELESS
    config      = ConnectionConfig(),    # optional — all defaults shown below
)

# Async
ctx = await redfish_sdk.connect_async(
    host="127.0.0.1", port=8000,
    credentials=Credentials("admin", "password"),
    auth_mode=AuthMode.SESSION,
)
```

### ConnectionConfig defaults

```python
ConnectionConfig(
    use_tls                = True,   # False = plain HTTP (simulators, some lab setups)
    verify_tls             = True,   # False = accept self-signed certs (dev only, never production)
    tls_ca_cert            = None,   # path to custom CA cert file
    connect_timeout_sec    = 10.0,
    request_timeout_sec    = 30.0,
    task_poll_interval_sec = 5.0,
    task_timeout_sec       = 300.0,
    base_path_override     = None,   # override /redfish/v1 if needed
)
```

> **`use_tls` vs `verify_tls`:** `use_tls=False` uses plain HTTP — the server
> never sees a TLS handshake. `verify_tls=False` uses HTTPS but skips cert
> validation. Use `use_tls=False` for the DMTF mockup server. Use
> `verify_tls=False` for real BMCs with self-signed certs in a lab.

### Exceptions raised by connect()

| Exception | When |
|---|---|
| `RedfishConnectionError` | Host unreachable |
| `RedfishTLSError` | TLS certificate rejected |
| `RedfishAuthError` | Wrong credentials (401/403) |
| `RedfishProtocolError` | Not a Redfish endpoint |

---

## ClientContext

The handle returned by `connect()`. Pass it around — never construct it directly.

```python
ctx.is_connected    # bool
ctx.base_url        # "https://127.0.0.1:8000"

ctx.close()         # closes session, releases connection
await ctx.close_async()
```

---

## RedfishResponse

Every SDK call returns a `RedfishResponse`.

```python
response = ctx.get("/redfish/v1/Systems/1")

response.success        # True if HTTP 2xx
response.status_code    # 200, 201, 202, 404 ...
response.body           # parsed JSON dict / list, or None
response.headers        # dict[str, str] — lowercase keys
response.extended_info  # list[RedfishMessage] from @Message.ExtendedInfo
response.task           # RedfishTask if status was 202, else None
response.raw            # raw response body string
```

**404 is never an exception.** It returns a response with `success=False`.

```python
r = ctx.get("/redfish/v1/Systems/does-not-exist")
if not r.success:
    print(f"Not found: {r.status_code}")
```

---

## Direct HTTP Access

Use these when you need to call any URI directly — OEM resources, custom
paths, anything not covered by a service handle.

```python
# Sync
r = ctx.get("/redfish/v1/Systems")
r = ctx.post("/redfish/v1/Systems/1/Actions/Reset", body={"ResetType": "GracefulRestart"})
r = ctx.patch("/redfish/v1/Systems/1", body={"AssetTag": "rack-42"})
r = ctx.delete("/redfish/v1/SessionService/Sessions/1")

# Async
r = await ctx.get_async("/redfish/v1/Systems")
r = await ctx.post_async("/redfish/v1/Systems/1/Actions/Reset", body={...})
r = await ctx.patch_async("/redfish/v1/Systems/1", body={...})
r = await ctx.delete_async("/redfish/v1/SessionService/Sessions/1")
```

---

## Discovery

Walks the Redfish service tree to find what's available.

```python
disc = ctx.discovery

# Root — enumerate ServiceRoot links only, no traversal
result = disc.root()

# Partial — resolve one specific service
result = disc.partial("EventService")

# Full — resolve all top-level services
result = disc.full()

# Async variants
result = await disc.full_async()

# Query results
result.has_service("TelemetryService")      # True / False
result.service_uri("EventService")          # "/redfish/v1/EventService"
result.capabilities                         # ["EventService", "LogService", ...]
result.services                             # {"EventService": "/redfish/v1/EventService", ...}
```

Discovery populates an internal map — service handles use it automatically
to resolve their URIs without re-fetching ServiceRoot.

---

## EventService

```python
svc = ctx.event_service

# Query service capabilities
r = svc.get_service_info()

# Subscribe — BMC will POST events to your listener URL
r = svc.subscribe(
    destination      = "http://my-host:9090/events",
    event_types      = ["Alert", "ResourceUpdated"],    # optional
    registry_prefixes= ["OpenBMC", "Base"],             # optional
    message_ids      = [],                              # optional
    context          = "my-client-context",             # optional string passed back with events
)
print(r.body)   # contains subscription URI

# List, inspect, delete subscriptions
r = svc.list_subscriptions()
r = svc.get_subscription("/redfish/v1/EventService/Subscriptions/1")
r = svc.delete_subscription("/redfish/v1/EventService/Subscriptions/1")

# SSE streaming (simulator / test environments)
async for event in svc.subscribe_sse():
    print(event.event_type, event.message)

# Submit a test event (simulator use)
r = svc.submit_test_event({"EventType": "Alert", "MessageId": "Base.1.8.GeneralError"})

# Async variants
r = await svc.subscribe_async(destination="http://my-host:9090/events")
r = await svc.list_subscriptions_async()
```

---

## LogService

```python
from redfish_sdk.services.log_service import LogFilter

svc = ctx.log_service

# Find all log services (walks Systems + Managers)
r = svc.list_services()
r = await svc.list_services_async()

# Single page — $top only
r = svc.get_entries(log_uri, filter=LogFilter(top=10))

# $skip + $top  (order enforced internally: $skip → $top → $filter)
r = svc.get_entries(log_uri, filter=LogFilter(skip=20, top=5))

# $filter by Severity
r = svc.get_entries(log_uri, filter=LogFilter(severity="Warning", top=10))

# $filter by MessageId
r = svc.get_entries(log_uri, filter=LogFilter(message_id="OpenBMC.0.4.DiscreteEventAsserted"))

# Raw OData $filter expression (escape-hatch — overrides severity/message_id)
r = svc.get_entries(log_uri, filter=LogFilter(odata_filter="MessageId eq 'Base.1.8.Success'"))

# Compound: skip + top + filter
r = svc.get_entries(log_uri, filter=LogFilter(skip=30, top=5, severity="Warning"))

# Auto-pagination — follows Members@odata.nextLink automatically
for page in svc.iter_entries(log_uri, filter=LogFilter(top=50), max_pages=10):
    for entry in page.body.get("Members", []):
        print(entry["MessageId"], entry["Severity"])

# Async variants
r = await svc.get_entries_async(log_uri, filter=LogFilter(skip=10, top=5))
async for page in svc.iter_entries_async(log_uri, filter=LogFilter(top=50), max_pages=10):
    for entry in page.body.get("Members", []):
        print(entry["MessageId"], entry["Severity"])

# Single entry
r = svc.get_entry("/redfish/v1/Systems/1/LogServices/EventLog/Entries/1")
r = await svc.get_entry_async(entry_uri)

# Clear a log
r = svc.clear_log("/redfish/v1/Systems/1/LogServices/EventLog")
r = await svc.clear_log_async(log_uri)
```

> **LogFilter fields** (all optional, all default `None`):
>
> | Field | OData param | Notes |
> |---|---|---|
> | `top` | `$top` | Max entries per page |
> | `skip` | `$skip` | Entries to skip (offset) |
> | `severity` | `$filter=Severity eq '…'` | e.g. `"Warning"`, `"Critical"` |
> | `message_id` | `$filter=MessageId eq '…'` | Full MessageId string |
> | `odata_filter` | `$filter=…` | Raw expression; overrides severity/message_id |
>
> Parameter order always emitted as **`$skip → $top → $filter`** (required by OpenBMC).

---

## TelemetryService

```python
svc = ctx.telemetry_service

# Service info
r = svc.get_service_info()

# Metric Report Definitions — what the BMC can report
r = svc.list_metric_report_definitions()
r = svc.get_metric_report_definition("/redfish/v1/TelemetryService/MetricReportDefinitions/All")

# Metric Reports — actual data
r = svc.list_metric_reports()
r = svc.get_metric_report("/redfish/v1/TelemetryService/MetricReports/All")

# SSE streaming
async for report in svc.stream_metric_reports():
    for value in report.metric_values:
        print(f"{value.metric_id}: {value.metric_value}")

# Stream for a specific definition
async for report in svc.stream_metric_reports(definition_uri="..."):
    ...

# Async variants
r = await svc.get_service_info_async()
r = await svc.get_metric_report_async(report_uri)
```

---

## UpdateService

```python
svc = ctx.update_service

# Inventory
r = svc.list_firmware_inventory()
r = svc.get_firmware_component("/redfish/v1/UpdateService/FirmwareInventory/BMC")
r = svc.list_software_inventory()

# Initiate update — returns 202 with a task if the BMC accepts it
r = svc.simple_update(
    image_uri         = "http://my-server/firmware.bin",
    targets           = ["/redfish/v1/UpdateService/FirmwareInventory/BMC"],
    transfer_protocol = "HTTP",
    apply_time        = "Immediate",
)

if r.task:
    final = r.task.wait()       # blocks until complete or timeout
    print(final.body)

# Async
r = await svc.simple_update_async(image_uri="http://...")
if r.task:
    final = await r.task.wait_async()
```

---

## Tasks

When a BMC operation returns `202 Accepted`, the response includes a
`RedfishTask`. You drive it:

```python
# Wait until done (blocks / awaits)
final = response.task.wait()
final = await response.task.wait_async()

# Override timeouts
final = response.task.wait(poll_interval_sec=2.0, timeout_sec=600.0)

# Monitor with a callback on each state change
def on_change(state, task):
    print(f"Task state → {state}  ({task.percent_complete}%)")

await response.task.monitor_async(on_change)

# Async callback also works
async def on_change_async(state, task):
    await log_to_db(state)

await response.task.monitor_async(on_change_async)

# Cancel
r = response.task.cancel()
r = await response.task.cancel_async()

# Task fields
response.task.task_uri          # "/redfish/v1/TaskService/Tasks/1"
response.task.task_id           # "1"
response.task.state             # TaskState.RUNNING
response.task.percent_complete  # 42 or None
response.task.messages          # list[RedfishMessage]
```

### TaskState values

```
New  Starting  Running  Suspended  Interrupted  Pending  Stopping
Completed  Killed  Exception  Service  Cancelling  Cancelled
```

Terminal states: `Completed`, `Killed`, `Exception`, `Cancelled`

---

## RedfishEventListener

A standalone embedded HTTP server that receives push event deliveries
from the BMC. Independent of `ClientContext` — create it separately.

```python
from redfish_sdk import RedfishEventListener

listener = RedfishEventListener(port=9090)

# Optional: wire to context for MessageRegistry decoding
listener.use_context(ctx)

# Register callbacks
listener.on_event(lambda event: print(event.message))

# Filter by EventType
listener.on_event_type("Alert", lambda event: print("ALERT:", event.message_id))

# Filter by registry prefix
listener.on_registry("OpenBMC", lambda event: print("OpenBMC event:", event.message))

# Async callbacks work too
async def handle(event):
    await store_in_db(event)

listener.on_event(handle)

# Start / stop
listener.start()        # non-blocking — starts background server
listener.stop()         # graceful shutdown

# With TLS (real BMC push delivery requires HTTPS destination)
listener = RedfishEventListener(
    port     = 9090,
    host     = "0.0.0.0",
    tls_cert = "/path/to/cert.pem",
    tls_key  = "/path/to/key.pem",
)

# State
listener.is_running     # True / False
listener.listen_url     # "http://0.0.0.0:9090"
```

### RedfishEvent fields

```python
event.event_id              # "1"
event.event_type            # "Alert"
event.event_timestamp       # "2026-03-04T12:00:00Z"
event.message_id            # "OpenBMC.0.4.0.CPERError"
event.message               # decoded human-readable text
event.severity              # "Critical"
event.origin_of_condition   # "/redfish/v1/Systems/1" or None
event.raw                   # full raw event JSON dict
```

---

## Error Handling

```python
from redfish_sdk.errors import (
    RedfishSDKError,
    RedfishConnectionError,
    RedfishTLSError,
    RedfishAuthError,
    RedfishProtocolError,
    RedfishTaskTimeoutError,
    RedfishTaskFailedError,
)

try:
    ctx = redfish_sdk.connect(host="bmc.local", port=443,
                              credentials=Credentials("admin", "wrong"),
                              auth_mode=AuthMode.SESSION)
except RedfishAuthError as e:
    print(f"Bad credentials: {e}")
except RedfishConnectionError as e:
    print(f"Cannot reach host: {e}")
except RedfishSDKError as e:
    print(f"SDK error: {e}")
```

```python
try:
    final = response.task.wait(timeout_sec=60.0)
except RedfishTaskTimeoutError as e:
    print(f"Timed out. Last state: {e.task.state}")
except RedfishTaskFailedError as e:
    print(f"Task failed: {e.task.state}")
```

---

## Async Usage

All sync methods have an `_async` variant. Use them when running inside
an existing event loop (FastAPI, Jupyter, asyncio applications).

```python
import asyncio
import redfish_sdk

async def main():
    ctx = await redfish_sdk.connect_async(
        host="127.0.0.1", port=8000,
        credentials=Credentials("admin", "password"),
        auth_mode=AuthMode.SESSION,
    )
    r = await ctx.get_async("/redfish/v1/Systems")
    print(r.body)
    await ctx.close_async()

asyncio.run(main())
```

Calling a sync method from inside a running event loop raises a clear
error directing you to the `_async` variant.

---

## Typical Patterns

### Connect, discover, work, close

```python
ctx = redfish_sdk.connect(...)
try:
    result = ctx.discovery.full()
    if result.has_service("TelemetryService"):
        r = ctx.telemetry_service.list_metric_reports()
        ...
finally:
    ctx.close()
```

### Context manager style (coming in v0.2)

Not yet implemented — use `try/finally` for now.

### Multiple BMC connections

```python
ctx1 = redfish_sdk.connect(host="bmc-1.local", ...)
ctx2 = redfish_sdk.connect(host="bmc-2.local", ...)

r1 = ctx1.get("/redfish/v1/Systems")
r2 = ctx2.get("/redfish/v1/Systems")

ctx1.close()
ctx2.close()
```

Each context is independent — no shared state.

---

## Running the Samples

All samples target the simulator at `127.0.0.1:8000`.

```bash
# Start the simulator first
cd /path/to/bmc-redfish-simulator && python main.py

# Install the SDK
cd python/ && pip install -e .

# Run any sample
python samples/01_connect_discover.py
python samples/05_event_subscribe.py
python samples/09_telemetry.py
```

See [samples/README.md](../samples/README.md) for the full list.
