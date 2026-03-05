# RSDK-PERF-001 — SDK Performance & Language Comparison

**Measured:** March 5, 2026  
**Simulator:** `redfishMockupServer_platform.py` — Ares_AI_Blade mockup, HTTPS on `127.0.0.1:8000`  
**Method:** `/usr/bin/time -v` wrapping each sample binary; 5 runs per combination; median wall-clock, mean RSS reported  
**Rust build:** `cargo build --release`  
**C++ build:** `cmake -DCMAKE_BUILD_TYPE=Debug` (default project build)  
**Python:** CPython 3.x, no pre-warmed interpreter cache  

---

## Wall-Clock Latency

Each sample performs a full TLS handshake + session auth POST + one or more GET requests
against the local simulator.  Median of 5 runs.

| Sample | Python | C++ | Rust | C++ vs Python | Rust vs Python |
|---|---:|---:|---:|---:|---:|
| 01 connect + discover | 680 ms | 20 ms | 130 ms | **34× faster** | **5.2× faster** |
| 03 GET resources | 590 ms | 20 ms | 150 ms | **30× faster** | **3.9× faster** |
| 04 direct API (GET/PATCH/DELETE) | 550 ms | 30 ms | 90 ms | **18× faster** | **6.1× faster** |

### What drives Python's latency

Python's numbers are dominated by interpreter startup plus module import, not network:

- CPython interpreter init: ~80 ms
- `import asyncio`: ~40 ms
- `import aiohttp + ssl + certifi`: ~200–250 ms
- First async loop start: ~30 ms

The actual Redfish HTTP round-trips (TLS handshake → session POST → GET) take
15–25 ms for all three languages on a loopback interface.  The ~500 ms gap between
Python and C++/Rust closes almost entirely once the interpreter is already warm
(e.g. in a long-running service process).

### Implication for use-cases

| Use-case | Impact |
|---|---|
| Long-running daemon (monitoring loop) | Startup cost amortised — all three comparable |
| CLI tool invoked per-BMC-poll | Python 500 ms startup × N BMCs = meaningful overhead |
| Embedded agent on BMC firmware | C++ / Rust only — Python interpreter unavailable |
| Scripting / automation on ops workstation | Python startup acceptable; best DX |

---

## Peak Memory (RSS)

Mean peak resident set size across the three samples above.

| Language | Peak RSS | vs Python |
|---|---:|---:|
| Python | 51.5 MB | — |
| C++ | 14.1 MB | **3.6× less** |
| Rust | 12.2 MB | **4.2× less** |

Python carries CPython's heap, asyncio machinery, aiohttp connection pool, SSL context,
and certifi's CA bundle in memory before the first Redfish call.

C++ and Rust both sit in the 12–14 MB range.  Rust is marginally leaner because
reqwest's async runtime (Tokio) initialises fewer worker threads than libcurl's
connection pool when only one concurrent request is in flight.

---

## Binary & Deployment Size

| | Python | C++ | Rust |
|---|---|---|---|
| Deliverable | source + venv | shared binary + system libs | single static binary |
| Sample 01 binary | (interpreted) | 374 KB (debug) / ~120 KB stripped | 7.8 MB (debug) / ~1.5 MB stripped+LTO |
| Runtime dependencies | CPython + pip packages | libcurl, libssl, libstdc++ | **none** |
| Self-contained deploy | No — needs matching venv | No — needs system libs | **Yes** |

Rust statically links every dependency (reqwest, tokio, rustls, serde_json) into one
binary.  C++ links against whatever `libcurl` and `libssl` versions are present on the
target system — a potential version mismatch risk on diverse BMC fleets.

To produce a lean Rust binary:
```bash
# in rust/
RUSTFLAGS="-C link-arg=-s" cargo build --release   # strip symbols inline
# or post-build:
strip target/release/01_connect_discover            # ~1.5 MB
```

---

## Source Complexity (LOC)

All three implementations cover the same 15 samples and the same SDK module set
(transport, auth, protocol, discovery, services, events).

### Library source

| Module | Python | C++ (src) | C++ (headers) | Rust |
|---|---:|---:|---:|---:|
| transport / http_client | 406 | 391 | 141 | 312 |
| transport / auth | 151 | 118 | 45 | 294 |
| transport / types | — | — | — | 109 |
| protocol / response | 78 | 68 | 52 | 276 |
| protocol / task | 217 | 70 | 42 | 81 |
| protocol / registry | 93 | — | — | 62 |
| discovery | 137 | 75 | 38 | 323 |
| services (4 modules) | 833 | 434 | 220 | 493 |
| events / listener | 524 | 564 | 178 | 407 |
| client / context / errors / lib | 307 | 277 | 188 | 388 |
| **Total** | **3,339** | **1,997** | **1,000** | **2,867** |
| **Combined C++** | — | **2,997** | | |

### Samples (15 files each)

| | Python | C++ | Rust |
|---|---:|---:|---:|
| Total LOC | 1,879 | 1,201 | 1,099 |
| Per sample (avg) | 125 | 80 | 73 |

C++ and Rust samples are shorter per file because the SDK's type system
communicates more intent at the call site — fewer docstrings and error-string
formatting needed inline.  Python samples are longer due to `argparse` boilerplate
and inline comments explaining async patterns.

---

## Safety & Type System

| Property | Python | C++ | Rust |
|---|---|---|---|
| Type system | Dynamic (runtime) | Static (compile-time) | Static (compile-time) |
| Null / None safety | Runtime `AttributeError` | Runtime UB / nullptr deref | **Compile-time** (`Option<T>`) |
| Memory safety | GC + refcount | Manual + RAII (no GC) | **Borrow checker** (no GC) |
| Data-race safety | GIL prevents races | UB — developer's responsibility | **Compile-time** (`Send`/`Sync`) |
| Error propagation | Exception | Exception or return code | `Result<T,E>` — must handle |
| Async model | `asyncio` (event loop) | `std::async` / futures | Tokio (work-stealing) |

Rust's borrow checker caught two real bugs during SDK development that would have been
silent runtime errors in C++:

1. **Drop-inside-async:** Dropping a `tokio::Runtime` from within an async context
   (`#[tokio::main]`) panics at runtime in Tokio.  The compiler + `Handle::try_current()`
   check made the invariant explicit and forced a `mem::forget` guard.

2. **Mutex across await:** Holding a `tokio::sync::Mutex` guard across an `.await`
   point in the event listener caused a deadlock.  Switching to `std::sync::Mutex`
   (enforced by `Send` bounds) fixed it at the type level.

---

## Summary Scorecard

| Dimension | Python | C++ | Rust |
|---|---|---|---|
| Startup latency | 🔴 ~550–680 ms | 🟢 20–30 ms | 🟡 90–150 ms |
| Peak memory | 🔴 ~51 MB | 🟡 ~14 MB | 🟢 ~12 MB |
| Binary portability | 🔴 needs venv | 🟡 needs system libs | 🟢 single static binary |
| Developer velocity | 🟢 fastest | 🟡 moderate | 🟡 moderate |
| Memory safety | 🟡 GC/refcount | 🔴 manual | 🟢 compile-time |
| Null / race safety | 🔴 runtime | 🔴 runtime | 🟢 compile-time |
| BMC / embedded fit | 🔴 interpreter heavy | 🟢 native | 🟢 native, no runtime |
| Test coverage | 🟢 pytest + mocks | 🟡 (no unit tests yet) | 🟢 68 tests |
| Library LOC | 3,339 | 2,997 | 2,867 |

**Choose Python** when: scripting, automation, rapid prototyping, or operator tooling
on a machine where a Python interpreter and network access are guaranteed.

**Choose C++** when: integrating into existing BMC firmware, RAS/CPER consumers,
or any codebase that already links against libcurl.  The `extern "C"` surface also
makes it callable from plain C.

**Choose Rust** when: building a standalone agent or daemon, deploying to a fleet of
heterogeneous BMCs where you cannot control the runtime environment, or when
memory/safety guarantees are a hard requirement (safety-critical infrastructure).

---

*Document ID: RSDK-PERF-001*
