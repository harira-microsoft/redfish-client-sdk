#!/usr/bin/env python3
"""Sample 03 — GET Systems, Chassis, and Managers collections.

Demonstrates:
  - ClientContext.systems / chassis / managers high-level helpers
  - Iterating collection members
  - Accessing individual member properties

Usage:
    python 03_get_resources.py [--host HOST] [--port PORT]
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
    p = argparse.ArgumentParser(description="Sample 03 — GET Resources")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    return p.parse_args()


def _print_members(label: str, response) -> list[dict]:
    """Print collection summary and return member list."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if not response.success:
        print(f"  [WARN] HTTP {response.status_code}")
        return []

    members = response.body.get("Members", [])
    count = response.body.get("Members@odata.count", len(members))
    print(f"  Members@odata.count : {count}")

    for m in members:
        print(f"    {m.get('@odata.id', '?')}")

    return members


async def main() -> None:
    args = parse_args()

    creds = Credentials(username=args.user, password=args.password)
    config = ConnectionConfig(verify_tls=not args.no_tls_verify, use_tls=not args.no_tls)

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
        await ctx.discover_async()

        # ── Systems ─────────────────────────────────────────────────────
        systems_resp = await ctx.get_async("/redfish/v1/Systems")
        members = _print_members("ComputerSystemCollection", systems_resp)

        # Fetch first system in detail
        if members:
            uri = members[0]["@odata.id"]
            sys_resp = await ctx.get_async(uri)
            if sys_resp.success:
                body = sys_resp.body
                print(f"\n  First System detail:")
                print(f"    Id              : {body.get('Id')}")
                print(f"    Name            : {body.get('Name')}")
                print(f"    Manufacturer    : {body.get('Manufacturer')}")
                print(f"    Model           : {body.get('Model')}")
                print(f"    SerialNumber    : {body.get('SerialNumber')}")
                print(f"    PowerState      : {body.get('PowerState')}")
                status = body.get("Status", {})
                print(f"    Status.State    : {status.get('State')}")
                print(f"    Status.Health   : {status.get('Health')}")

        # ── Chassis ─────────────────────────────────────────────────────
        chassis_resp = await ctx.get_async("/redfish/v1/Chassis")
        ch_members = _print_members("ChassisCollection", chassis_resp)

        if ch_members:
            uri = ch_members[0]["@odata.id"]
            ch_resp = await ctx.get_async(uri)
            if ch_resp.success:
                body = ch_resp.body
                print(f"\n  First Chassis detail:")
                print(f"    Id              : {body.get('Id')}")
                print(f"    ChassisType     : {body.get('ChassisType')}")
                print(f"    Manufacturer    : {body.get('Manufacturer')}")
                pwr = body.get("Power", {})
                print(f"    Power link      : {pwr.get('@odata.id', 'N/A')}")

        # ── Managers ────────────────────────────────────────────────────
        mgr_resp = await ctx.get_async("/redfish/v1/Managers")
        mgr_members = _print_members("ManagerCollection", mgr_resp)

        if mgr_members:
            uri = mgr_members[0]["@odata.id"]
            mgr_detail = await ctx.get_async(uri)
            if mgr_detail.success:
                body = mgr_detail.body
                print(f"\n  First Manager detail:")
                print(f"    Id              : {body.get('Id')}")
                print(f"    ManagerType     : {body.get('ManagerType')}")
                print(f"    FirmwareVersion : {body.get('FirmwareVersion')}")

        print("\n✓ Resource GET complete")


if __name__ == "__main__":
    asyncio.run(main())
