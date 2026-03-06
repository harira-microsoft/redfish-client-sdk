# Redfish SDK — Python Samples

This directory contains 15 runnable sample scripts that demonstrate the full
Redfish Client SDK feature surface.  Each script is self-contained and targets
the `bmc-redfish-simulator` but works against any real BMC as well.

## Prerequisites

```bash
# From the python/ directory
pip install -e ".[dev]"

# Start the simulator (in another terminal)
cd /path/to/bmc-redfish-simulator
python simulator.py          # default: 127.0.0.1:8000
```

## Common CLI options

Every sample accepts:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | BMC hostname or IP |
| `--port` | `8000` | BMC port |
| `--user` | `admin` | Username |
| `--password` | `password` | Password |
| `--no-tls-verify` | (flag) | Accept self-signed / any TLS cert (HTTPS only) |
| `--no-tls` | (flag) | Use plain HTTP instead of HTTPS — required for the DMTF mockup server |

## Samples

| # | File | Feature demonstrated |
|---|------|----------------------|
| 01 | `01_connect_discover.py` | Connect + full service discovery |
| 02 | `02_partial_discover.py` | Partial discovery (single service) |
| 03 | `03_get_resources.py` | GET Systems, Chassis, Managers |
| 04 | `04_direct_api.py` | Raw `get/post/patch/delete` via `ClientContext` |
| 05 | `05_event_subscribe.py` | Subscribe / list / delete subscriptions |
| 06 | `06_event_listener.py` | Start embedded listener + auto-subscribe |
| 07 | `07_event_monitor.py` | Listener with type and registry callbacks |
| 08 | `08_log_service.py` | List log services + paginated entry fetch |
| 09 | `09_telemetry.py` | Metric reports + SSE streaming |
| 10 | `10_update_service.py` | Firmware inventory + SimpleUpdate task |
| 11 | `11_task_polling.py` | Task wait + async monitor |
| 12 | `12_session_vs_stateless.py` | Session auth vs stateless Basic auth |
| 13 | `13_retry_and_refresh.py` | Connection retry + auth token refresh |
| 14 | `14_sel_parsing.py` | Parse raw SEL hex records (offline, no BMC needed) |
| 15 | `15_multipart_upload.py` | Multipart firmware upload |

## Running all samples

```bash
# Against the DMTF mockup server (plain HTTP)
for s in samples/0*.py; do
    echo "=== $s ==="; python "$s" --no-tls; echo
done

# Against a real BMC with self-signed cert
for s in samples/0*.py; do
    echo "=== $s ==="; python "$s" --host 192.168.1.100 --port 443 --no-tls-verify; echo
done
```
