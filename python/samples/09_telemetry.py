#!/usr/bin/env python3
"""Sample 09 — TelemetryService: metric reports and SSE streaming.

Demonstrates:
  - ctx.telemetry.list_metric_report_definitions_async()
  - ctx.telemetry.list_metric_reports_async()
  - ctx.telemetry.get_metric_report_async()
  - ctx.telemetry.stream_metric_reports() async generator

Usage:
    python 09_telemetry.py [--host HOST] [--port PORT]
                           [--stream-seconds SECONDS]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.errors import RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 09 — Telemetry")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument(
        "--stream-seconds",
        type=float,
        default=0.0,
        help="Seconds to stream metric SSE (0 = skip streaming)",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    creds = Credentials(username=args.user, password=args.password)
    config = ConnectionConfig(verify_tls=not args.no_tls_verify)

    try:
        ctx = await redfish_sdk.connect_async(
            host=args.host,
            port=args.port,
            credentials=creds,
            auth_mode=AuthMode.SESSION,
            config=config,
        )
    except RedfishConnectionError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    async with ctx:
        tel = ctx.telemetry

        # ── Metric Report Definitions ────────────────────────────────────
        print("Listing metric report definitions …")
        defs_resp = await tel.list_metric_report_definitions_async()
        if defs_resp.success:
            defs = defs_resp.body.get("Members", [])
            print(f"  Count: {len(defs)}")
            for d in defs[:5]:
                print(f"    {d.get('@odata.id')}")
        else:
            print(f"  ✗ HTTP {defs_resp.status_code}")

        # ── Metric Reports ───────────────────────────────────────────────
        print("\nListing metric reports …")
        reports_resp = await tel.list_metric_reports_async()
        if not reports_resp.success:
            print(f"  ✗ HTTP {reports_resp.status_code} — TelemetryService may not be present")
            print("\n✓ Telemetry sample complete (limited support on this endpoint)")
            return

        reports = reports_resp.body.get("Members", [])
        print(f"  Count: {len(reports)}")
        for r in reports[:5]:
            print(f"    {r.get('@odata.id')}")

        # ── Get first report in detail ───────────────────────────────────
        if reports:
            report_uri = reports[0].get("@odata.id", "")
            print(f"\nFetching report detail: {report_uri}")
            report_resp = await tel.get_metric_report_async(report_uri)
            if report_resp.success:
                report = report_resp  # MetricReport dataclass
                # The get call returns a MetricReport object
                print(f"  Name            : {report.body.get('Name') if hasattr(report, 'body') else '?'}")
                # Actual MetricReport dataclass fields
                if hasattr(report, 'name'):
                    print(f"  Name            : {report.name}")
                    print(f"  Timestamp       : {report.timestamp}")
                    print(f"  MetricValues    : {len(report.metric_values)} value(s)")
                    for mv in report.metric_values[:5]:
                        print(f"    {mv.metric_id:<40} = {mv.value}  ({mv.timestamp})")
            else:
                print(f"  ✗ HTTP {report_resp.status_code}")

        # ── SSE streaming (optional) ─────────────────────────────────────
        if args.stream_seconds > 0 and reports:
            report_uri = reports[0].get("@odata.id", "")
            # Build SSE URL from report definition
            sse_url = report_uri  # TelemetryService SSE is on the report URI with Accept: text/event-stream
            print(f"\nStreaming metric SSE from {sse_url} for {args.stream_seconds}s …")
            count = 0
            try:
                async with asyncio.timeout(args.stream_seconds):
                    async for report in tel.stream_metric_reports(sse_url):
                        count += 1
                        print(f"  [SSE {count}] {report.name}  {report.timestamp}")
                        for mv in report.metric_values[:3]:
                            print(f"    {mv.metric_id} = {mv.value}")
            except TimeoutError:
                pass
            except Exception as exc:  # noqa: BLE001
                print(f"  SSE ended: {exc}")
            print(f"  Received {count} SSE report(s)")

        print("\n✓ Telemetry sample complete")


if __name__ == "__main__":
    asyncio.run(main())
