#!/usr/bin/env python3
"""Sample 02 — Partial discovery (single service tree walk).

Demonstrates:
  - ClientContext.discover_async(service="Systems")
  - DiscoveryResult.service_uri()
  - Re-running partial discovery for a second service

Usage:
    python 02_partial_discover.py [--host HOST] [--port PORT]
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
    p = argparse.ArgumentParser(description="Sample 02 — Partial Discovery")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
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
        # ── Partial: only walk Systems ──────────────────────────────────
        print("Partial discovery — Systems only …")
        result = await ctx.discover_async(service="Systems")

        systems_uri = result.service_uri("Systems")
        if systems_uri:
            print(f"  Systems URI: {systems_uri}")
        else:
            print("  Systems not found on this endpoint")

        # ── Partial: EventService ───────────────────────────────────────
        print("\nPartial discovery — EventService only …")
        result2 = await ctx.discover_async(service="EventService")

        events_uri = result2.service_uri("EventService")
        if events_uri:
            print(f"  EventService URI: {events_uri}")
        else:
            print("  EventService not available on this endpoint")

        # ── Root info only ──────────────────────────────────────────────
        print("\nFetching root info (no tree walk) …")
        root_result = await ctx.discover_async(root_only=True)
        caps = root_result.capabilities
        print(f"  Redfish version : {caps.redfish_version}")
        print(f"  Product         : {caps.product}")

        print("\n✓ Partial discovery complete")


if __name__ == "__main__":
    asyncio.run(main())
