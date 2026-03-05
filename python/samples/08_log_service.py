#!/usr/bin/env python3
"""Sample 08 — LogService: query with $top/$skip/$filter, pagination.

Demonstrates:
  - ctx.logs.list_services_async()
  - LogFilter with top, skip, severity, message_id (OData order enforced)
  - ctx.logs.get_entries_async() — single page
  - ctx.logs.iter_entries_async() — follow Members@odata.nextLink
  - ctx.logs.get_entry_async()
  - ctx.logs.clear_log_async()

Usage:
    python 08_log_service.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.services.log_service import LogFilter
from redfish_sdk.errors import RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 08 — Log Service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--max-entries", type=int, default=5, help="Max entries to display per log")
    return p.parse_args()


def _print_entry(entry: dict) -> None:
    eid      = entry.get("Id", "?")
    severity = entry.get("Severity", entry.get("MessageSeverity", "?"))
    msg      = entry.get("Message", "")[:72]
    created  = entry.get("Created", "")[:19]
    print(f"      [{eid:>10}] {severity:<12} {created}  {msg}")


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
        logs = ctx.logs

        # ── List log services ──────────────────────────────────────────────
        print("Listing available log services …")
        svc_resp = await logs.list_services_async()
        if not svc_resp.success:
            print(f"  ✗ HTTP {svc_resp.status_code}")
            return

        services = svc_resp.body.get("Members", [])
        print(f"  Found {len(services)} log service(s)")

        for svc in services:
            svc_uri = svc.get("@odata.id", "")

            # ── Fetch entries (unfiltered, capped at max-entries) ────────
            filt = LogFilter(top=args.max_entries)
            entries_resp = await logs.get_entries_async(svc_uri, filter=filt)
            if not entries_resp.success:
                print(f"    ✗ Entries HTTP {entries_resp.status_code}")
                continue

            entries = entries_resp.body.get("Members", [])
            total = entries_resp.body.get("Members@odata.count", len(entries))
            print(f"    Total entries : {total}  (showing up to {args.max_entries})")

            for entry in entries[:args.max_entries]:
                eid = entry.get("Id", "?")
                severity = entry.get("Severity", entry.get("MessageSeverity", "?"))
                msg = entry.get("Message", "")[:80]
                created = entry.get("Created", "")
                print(f"    [{eid:>6}] {severity:<12} {created[:19]}  {msg}")

            # ── Fetch single entry in detail ─────────────────────────────
            if entries:
                entry_uri = entries[0].get("@odata.id")
                if entry_uri:
                    single_resp = await logs.get_entry_async(entry_uri)
                    if single_resp.success:
                        body = single_resp.body
                        print(f"\n    Entry detail ({entry_uri}):")
                        print(f"      MessageId   : {body.get('MessageId')}")
                        print(f"      MessageArgs : {body.get('MessageArgs')}")
                        print(f"      EntryCode   : {body.get('EntryCode')}")
                        print(f"      SensorType  : {body.get('SensorType')}")

            # ── Filter by severity ───────────────────────────────────────
            print(f"\n    Fetching Critical entries …")
            crit_filter = LogFilter(severity="Critical", top=3)
            crit_resp = await logs.get_entries_async(svc_uri, filter=crit_filter)
            if crit_resp.success:
                crit_entries = crit_resp.body.get("Members", [])
                print(f"    Critical count : {len(crit_entries)}")

        # ── Clear first log (simulator may not support this) ─────────────
        if services:
            first_log_uri = services[0].get("@odata.id", "")
            print(f"\nAttempting to clear log: {first_log_uri}")
            clear_resp = await logs.clear_log_async(first_log_uri)
            if clear_resp.success:
                print("  ✓ Log cleared")
            else:
                print(f"  ✗ HTTP {clear_resp.status_code} (may not be supported by simulator)")

        print("\n✓ Log service sample complete")


if __name__ == "__main__":
    asyncio.run(main())
