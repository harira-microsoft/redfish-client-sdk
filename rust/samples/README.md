# Redfish SDK — Rust Samples

15 runnable samples demonstrating the full Rust SDK surface. Each is a
standalone `async main()` binary compiled by Cargo.

## Build

```bash
# Install Rust toolchain (one-time)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# From rust/  — build all 15 samples in release mode
cargo build --release

# Or build a single sample
cargo build --release --bin 01_connect_discover
```

Binaries land in `rust/target/release/`.

## CLI Arguments

All samples use named flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | BMC hostname or IP |
| `--port` | `8000` | BMC port |
| `--user` | `admin` | Username |
| `--password` | `password` | Password |
| `--no-tls-verify` | (flag) | Accept self-signed / any TLS cert |
| `--no-tls` | (flag) | Use plain HTTP instead of HTTPS |

> Use `--no-tls` when pointing at the DMTF mockup server (plain HTTP).  
> Use `--no-tls-verify` for real BMCs with self-signed certificates.

Samples 06 and 07 (event listener) also accept:

| Flag | Default | Description |
|------|---------|-------------|
| `--listen-port` | `9090` / `9091` | Local listener port |
| `--wait` | `10` / `15` | Seconds to wait for events |

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
| 14 | `14_sel_parsing` | Parse raw SEL hex records (offline, no BMC needed) |
| 15 | `15_multipart_upload` | Multipart firmware upload |

## Running Against the Simulator

```bash
# Start simulator (separate terminal)
pip install redfish-mockup-server
redfish-mockup-server --host 127.0.0.1 --port 8000

# Run samples
./target/release/01_connect_discover --host 127.0.0.1 --port 8000 --no-tls
./target/release/03_get_resources    --host 127.0.0.1 --port 8000 --no-tls
./target/release/08_log_service      --host 127.0.0.1 --port 8000 --no-tls

# Samples 06/07 run a local event listener — use Ctrl+C to stop
./target/release/06_event_listener --host 127.0.0.1 --port 8000 --no-tls

# Sample 14 is fully offline (no BMC needed)
./target/release/14_sel_parsing
```

## Real BMC Hardware

```bash
# Real BMC with self-signed cert (lab)
./target/release/01_connect_discover \
    --host BMC_HOST --port 443 \
    --user admin --password yourpassword \
    --no-tls-verify

# Production BMC with valid CA cert
./target/release/01_connect_discover \
    --host bmc.datacenter.local --port 443 \
    --user admin --password yourpassword
# (SDK uses system trust store by default — no extra flag needed)
```

## Run the Test Suite

```bash
# From rust/ — 68 unit tests, no BMC required
cargo test

# Verbose output with test names
cargo test -- --nocapture
```

## Run All Samples

```bash
for sample in 01 03 04 05 08 09 11 12 13 14; do
    echo "=== $sample ==="
    ./target/release/${sample}_* --host 127.0.0.1 --port 8000 --no-tls
    echo
done
```

## `cargo run` Shortcut

During development you can run a sample without a separate build step:

```bash
cargo run --release --bin 01_connect_discover -- \
    --host 127.0.0.1 --port 8000 --no-tls
```

## API Reference

See the inline rustdoc:

```bash
cargo doc --open
```

Or read the crate source at `rust/redfish-sdk/src/lib.rs` — the module-level
docs cover every public type and function.
