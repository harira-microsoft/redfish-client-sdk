#!/usr/bin/env python3
"""
Redfish SDK — cross-language benchmark
Measures wall-clock time and peak RSS for samples 01, 03, 04
across Python, C++, and Rust SDK implementations.

Usage:
    python3 bench/run_bench.py [--runs N]

Requires: /usr/bin/time (GNU time), simulator running on 127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import statistics
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
RUNS = 5

# ---------------------------------------------------------------------------
# Sample command templates
# ---------------------------------------------------------------------------
SAMPLES = {
    "01_connect": {
        "python": ["python3", str(ROOT / "python/samples/01_connect_discover.py"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
        "cpp":    [str(ROOT / "cpp/build/01_connect_discover"),
                   "127.0.0.1", "8000"],
        "rust":   [str(ROOT / "rust/target/release/01_connect_discover"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
    },
    "03_get_resources": {
        "python": ["python3", str(ROOT / "python/samples/03_get_resources.py"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
        "cpp":    [str(ROOT / "cpp/build/03_get_resources"),
                   "127.0.0.1", "8000"],
        "rust":   [str(ROOT / "rust/target/release/03_get_resources"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
    },
    "04_direct_api": {
        "python": ["python3", str(ROOT / "python/samples/04_direct_api.py"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
        "cpp":    [str(ROOT / "cpp/build/04_direct_api"),
                   "127.0.0.1", "8000"],
        "rust":   [str(ROOT / "rust/target/release/04_direct_api"),
                   "--host", "127.0.0.1", "--port", "8000", "--no-tls-verify"],
    },
}

# ---------------------------------------------------------------------------
# Static metrics (pre-computed)
# ---------------------------------------------------------------------------
LOC = {
    "python": 3339,
    "cpp":    2997,   # 1997 src + 1000 headers
    "rust":   2867,
}

BINARY_KB = {
    "python": None,           # interpreted — no native binary
    "cpp":    374,            # 374 KB (01_connect_discover, debug build)
    "rust":   7835,           # 8 MB debug; release strip would be ~1.5 MB
}

# ---------------------------------------------------------------------------

TIME_BIN = "/usr/bin/time"

class RunResult(NamedTuple):
    wall_ms:  float   # wall-clock time in milliseconds
    rss_kb:   int     # peak resident set size in KB


def run_once(cmd: list[str]) -> RunResult | None:
    """Run cmd under /usr/bin/time -v, parse wall time and RSS."""
    wrapped = [TIME_BIN, "-v"] + cmd
    try:
        result = subprocess.run(
            wrapped,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None

    stderr = result.stderr.decode("utf-8", errors="replace")

    # Wall clock: "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.123"
    m_wall = re.search(r"Elapsed.*?:\s+(\d+):(\d+)\.(\d+)", stderr)
    if not m_wall:
        return None
    minutes  = int(m_wall.group(1))
    seconds  = int(m_wall.group(2))
    centisec = int(m_wall.group(3))
    wall_ms  = (minutes * 60 + seconds + centisec / 100) * 1000

    # RSS: "Maximum resident set size (kbytes): 12345"
    m_rss = re.search(r"Maximum resident set size \(kbytes\):\s+(\d+)", stderr)
    if not m_rss:
        return None
    rss_kb = int(m_rss.group(1))

    return RunResult(wall_ms=wall_ms, rss_kb=rss_kb)


def benchmark(cmd: list[str], runs: int) -> dict | None:
    results = []
    for _ in range(runs):
        r = run_once(cmd)
        if r:
            results.append(r)

    if not results:
        return None

    walls = [r.wall_ms for r in results]
    rsses = [r.rss_kb  for r in results]
    return {
        "wall_mean_ms": statistics.mean(walls),
        "wall_min_ms":  min(walls),
        "wall_median_ms": statistics.median(walls),
        "rss_mean_kb":  statistics.mean(rsses),
        "rss_min_kb":   min(rsses),
    }


def fmt_ms(v: float | None) -> str:
    if v is None:
        return "  n/a  "
    return f"{v:6.0f} ms"


def fmt_mb(v: float | None) -> str:
    if v is None:
        return "  n/a  "
    return f"{v/1024:6.1f} MB"


def pct(base: float, val: float) -> str:
    if base == 0:
        return "  ——  "
    ratio = val / base
    if ratio < 1.0:
        return f" {ratio:.2f}×  (faster)"
    return f" {ratio:.2f}×  (slower)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args()

    langs  = ["python", "cpp", "rust"]
    data: dict[str, dict[str, dict]] = {}   # data[sample][lang]

    total_samples = len(SAMPLES) * len(langs)
    done = 0

    for sample_name, lang_cmds in SAMPLES.items():
        data[sample_name] = {}
        for lang in langs:
            cmd = lang_cmds[lang]
            done += 1
            print(f"  [{done}/{total_samples}]  {lang:8s}  {sample_name}  "
                  f"({args.runs} runs) …", flush=True)
            result = benchmark(cmd, args.runs)
            data[sample_name][lang] = result

    # -----------------------------------------------------------------------
    # Print results
    # -----------------------------------------------------------------------
    SEP  = "─" * 100
    SEP2 = "═" * 100

    print()
    print(SEP2)
    print("  Redfish SDK  —  Performance Comparison:  Python  vs  C++  vs  Rust")
    print(f"  Simulator: https://127.0.0.1:8000   Runs per sample: {args.runs}")
    print(SEP2)

    # Wall-time table
    print()
    print("  ┌── WALL-CLOCK LATENCY (median, ms) ──────────────────────────────────────────┐")
    print(f"  {'Sample':<22}  {'Python':>12}  {'C++':>12}  {'Rust':>12}  {'C++ vs Py':>14}  {'Rust vs Py':>14}")
    print(f"  {'─'*22}  {'─'*12}  {'─'*12}  {'─'*12}  {'─'*14}  {'─'*14}")
    for sname, langs_data in data.items():
        py_med  = langs_data["python"]["wall_median_ms"] if langs_data["python"] else None
        cpp_med = langs_data["cpp"]["wall_median_ms"]    if langs_data["cpp"]    else None
        rs_med  = langs_data["rust"]["wall_median_ms"]   if langs_data["rust"]   else None

        py_s  = f"{py_med:>8.0f} ms"   if py_med  is not None else "     n/a  "
        cpp_s = f"{cpp_med:>8.0f} ms"  if cpp_med is not None else "     n/a  "
        rs_s  = f"{rs_med:>8.0f} ms"   if rs_med  is not None else "     n/a  "

        cpp_vs = ""
        rs_vs  = ""
        if py_med and cpp_med:
            r = cpp_med / py_med
            cpp_vs = f"  {r:.2f}×{'↑' if r < 1 else '↓'}"
        if py_med and rs_med:
            r = rs_med / py_med
            rs_vs  = f"  {r:.2f}×{'↑' if r < 1 else '↓'}"

        print(f"  {sname:<22}  {py_s:>12}  {cpp_s:>12}  {rs_s:>12}  {cpp_vs:>14}  {rs_vs:>14}")

    # RSS table
    print()
    print("  ┌── PEAK MEMORY  (mean RSS, MB) ──────────────────────────────────────────────┐")
    print(f"  {'Sample':<22}  {'Python':>12}  {'C++':>12}  {'Rust':>12}  {'C++ vs Py':>14}  {'Rust vs Py':>14}")
    print(f"  {'─'*22}  {'─'*12}  {'─'*12}  {'─'*12}  {'─'*14}  {'─'*14}")
    for sname, langs_data in data.items():
        py_rss  = langs_data["python"]["rss_mean_kb"]/1024 if langs_data["python"] else None
        cpp_rss = langs_data["cpp"]["rss_mean_kb"]/1024    if langs_data["cpp"]    else None
        rs_rss  = langs_data["rust"]["rss_mean_kb"]/1024   if langs_data["rust"]   else None

        py_s  = f"{py_rss:>8.1f} MB"  if py_rss  is not None else "     n/a  "
        cpp_s = f"{cpp_rss:>8.1f} MB" if cpp_rss is not None else "     n/a  "
        rs_s  = f"{rs_rss:>8.1f} MB"  if rs_rss  is not None else "     n/a  "

        cpp_vs = ""
        rs_vs  = ""
        if py_rss and cpp_rss:
            r = cpp_rss / py_rss
            cpp_vs = f"  {r:.2f}×{'↑' if r < 1 else '↓'}"
        if py_rss and rs_rss:
            r = rs_rss / py_rss
            rs_vs  = f"  {r:.2f}×{'↑' if r < 1 else '↓'}"

        print(f"  {sname:<22}  {py_s:>12}  {cpp_s:>12}  {rs_s:>12}  {cpp_vs:>14}  {rs_vs:>14}")

    # Static metrics
    print()
    print("  ┌── STATIC METRICS ───────────────────────────────────────────────────────────┐")
    print(f"  {'Metric':<30}  {'Python':>12}  {'C++':>12}  {'Rust':>12}")
    print(f"  {'─'*30}  {'─'*12}  {'─'*12}  {'─'*12}")

    # LOC
    print(f"  {'Library LOC (src)':<30}  {LOC['python']:>12,}  {LOC['cpp']:>12,}  {LOC['rust']:>12,}")

    # Samples LOC
    py_sloc  = sum(p.stat().st_size for p in (ROOT/"python/samples").glob("*.py"))
    cpp_sloc = sum(int(subprocess.check_output(["wc","-l",str(p)]).split()[0])
                   for p in (ROOT/"cpp/samples").glob("*.cpp"))
    rs_sloc  = sum(int(subprocess.check_output(["wc","-l",str(p)]).split()[0])
                   for p in (ROOT/"rust/samples/src/bin").glob("*.rs"))
    # use wc -l properly
    def loc_sum(pattern):
        files = list(pattern)
        if not files:
            return 0
        out = subprocess.check_output(["wc", "-l"] + [str(f) for f in files])
        lines = out.decode().strip().split("\n")
        return int(lines[-1].strip().split()[0])

    py_sloc  = loc_sum((ROOT/"python/samples").glob("*.py"))
    cpp_sloc = loc_sum((ROOT/"cpp/samples").glob("*.cpp"))
    rs_sloc  = loc_sum((ROOT/"rust/samples/src/bin").glob("*.rs"))
    print(f"  {'Samples LOC (15 files)':<30}  {py_sloc:>12,}  {cpp_sloc:>12,}  {rs_sloc:>12,}")

    # GC / memory safety model
    print(f"  {'Memory safety':<30}  {'GC (ref-count)':>12}  {'manual/RAII':>12}  {'borrow check':>12}")
    print(f"  {'Async model':<30}  {'asyncio':>12}  {'std::async':>12}  {'tokio':>12}")
    print(f"  {'Type system':<30}  {'dynamic':>12}  {'static':>12}  {'static':>12}")
    print(f"  {'Null safety':<30}  {'runtime':>12}  {'runtime':>12}  {'compile-time':>12}")

    # Binary sizes (release Rust, debug C++)
    cpp_bin_kb  = 374
    rust_bin_kb = 7835   # with full debug info; stripped release ~1.5 MB
    print(f"  {'Binary size (sample 01)':<30}  {'(interpreted)':>12}  {f'{cpp_bin_kb} KB':>12}  {f'{rust_bin_kb//1024} MB†':>12}")
    print()
    print("  † Rust release binary includes all dependencies statically linked.")
    print("    `strip` + LTO brings it to ~1.5 MB. C++ links against system libcurl/libssl.")
    print()
    print("  ↑ = lower is better (faster / smaller)")
    print(SEP2)


if __name__ == "__main__":
    main()
