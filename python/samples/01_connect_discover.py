#!/usr/bin/env python3
"""Sample 01 — Connect and perform full service discovery.

Demonstrates:
  - redfish_sdk.connect()
  - ClientContext.discover_async() / discover()
  - Inspecting DiscoveryResult

Usage:
    python 01_connect_discover.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running directly from the samples/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.errors import RedfishConnectionError, RedfishTLSError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 01 — Connect & Discover")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    creds = Credentials(username=args.user, password=args.password)
    config = ConnectionConfig(verify_tls=not args.no_tls_verify, use_tls=not args.no_tls)

    print(f"Connecting to {args.host}:{args.port} …")

    try:
        ctx = await redfish_sdk.connect_async(
            host=args.host,
            port=args.port,
            credentials=creds,
            auth_mode=AuthMode.SESSION,
            config=config,
        )
    except RedfishConnectionError as exc:
        print(f"[ERROR] Connection failed: {exc}")
        sys.exit(1)
    except RedfishTLSError as exc:
        print(f"[ERROR] TLS error: {exc}")
        sys.exit(1)

    async with ctx:
        print("✓ Connected\n")

        # ── Full discovery ──────────────────────────────────────────────
        print("Running full service discovery …")
        result = await ctx.discover_async()

        print(f"\n{'Service':<30} {'URI'}")
        print("-" * 70)
        for svc_name, svc_uri in result.services.items():
            print(f"  {svc_name:<28} {svc_uri}")

        # ── Capabilities ────────────────────────────────────────────────
        caps = result.capabilities
        print(f"\nCapabilities:")
        print(f"  redfish_version : {caps.redfish_version}")
        print(f"  uuid            : {caps.uuid}")
        print(f"  product         : {caps.product}")
        print(f"  has_systems     : {result.has_service('Systems')}")
        print(f"  has_chassis     : {result.has_service('Chassis')}")
        print(f"  has_managers    : {result.has_service('Managers')}")
        print(f"  has_events      : {result.has_service('EventService')}")
        print(f"  has_tasks       : {result.has_service('Tasks')}")

        print("\n✓ Discovery complete")


if __name__ == "__main__":
    asyncio.run(main())
