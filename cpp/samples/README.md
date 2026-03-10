# Redfish SDK — C++ Samples

15 runnable samples demonstrating the full C++ SDK surface. Each is a
self-contained `main()` that targets any Redfish-compliant server.

## Build

```bash
# Ubuntu / Debian — install once
sudo apt install build-essential cmake libcurl4-openssl-dev \
                 libssl-dev nlohmann-json3-dev

# From cpp/
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel

# Debug build (sanitisers, assertions)
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
```

Binaries land in `cpp/build/`.

## CLI Arguments

C++ samples use positional arguments:

```
./build/<sample> [host] [port]
```

| Position | Default | Description |
|----------|---------|-------------|
| `argv[1]` | `127.0.0.1` | BMC hostname or IP |
| `argv[2]` | `8000` | BMC port |

Samples default to `use_tls=false` so they work against the plain-HTTP
mockup server out of the box. Change `config.use_tls = true` in the source
for real BMC hardware.

Samples 06 and 07 (event listener) accept two extra positional arguments:

| Position | Default | Description |
|----------|---------|-------------|
| `argv[3]` | `9090` / `9091` | Local listener port |
| `argv[4]` | `10` / `15` | Seconds to wait for events |

Sample 08 (log service) accepts `argv[3]` for max log entries to fetch.

## Samples

| # | Binary | Feature demonstrated |
|---|--------|----------------------|
| 01 | `01_connect_discover` | Connect + full service discovery |
| 02 | `02_partial_discover` | Partial discovery (single service) |
| 03 | `03_get_resources` | GET Systems, Chassis, Managers |
| 04 | `04_direct_api` | Raw `get/post/patch/delete` |
| 05 | `05_event_subscribe` | Subscribe / list / delete subscriptions |
| 06 | `06_event_listener` | Embedded listener + auto-subscribe |
| 07 | `07_event_monitor` | Listener with type and registry callbacks |
| 08 | `08_log_service` | List log services + paginated entry fetch |
| 09 | `09_telemetry` | Metric reports |
| 10 | `10_update_service` | Firmware inventory + SimpleUpdate |
| 11 | `11_task_polling` | Task wait + async monitor |
| 12 | `12_session_vs_stateless` | Session auth vs Basic auth |
| 13 | `13_retry_and_refresh` | Connection retry + auth refresh |
| 14 | `14_sel_parsing` | Parse raw SEL hex records |
| 15 | `15_multipart_upload` | Multipart firmware upload |

## Running Against the Simulator

```bash
# Start simulator (separate terminal)
pip install redfish-mockup-server
redfish-mockup-server --host 127.0.0.1 --port 8000

# Run samples (simulator is plain HTTP, samples default to that)
./build/01_connect_discover
./build/03_get_resources
./build/08_log_service 127.0.0.1 8000 10

# Samples 06/07 run a local event listener — use Ctrl+C to stop
./build/06_event_listener 127.0.0.1 8000 9090 10
```

## Real BMC Hardware

For a real BMC (iLO, iDRAC, AMI):

```cpp
// In the sample's main():
redfish::ConnectionConfig config;
config.use_tls    = true;
config.verify_tls = false;   // self-signed cert (lab)
// OR
config.verify_tls = true;
config.tls_ca_cert = "/etc/ssl/certs/my-datacenter-ca.crt";   // production
```

```bash
./build/01_connect_discover BMC_HOST 443
```

## Run All

```bash
for sample in build/0{1,3,4,5,8,9,11,12,13,14,15}_*; do
    echo "=== $sample ==="; "$sample"; echo
done
```

## API Reference

See [cpp/docs/api-guide.md](../docs/api-guide.md) for the complete C++ API
reference including all public headers, types, and exception hierarchy.
