# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

#!/usr/bin/env python3
"""Sample 10 — UpdateService: firmware/software inventory and SimpleUpdate.

Demonstrates:
  - ctx.update.list_firmware_inventory_async()
  - ctx.update.list_software_inventory_async()
  - ctx.update.simple_update_async()
  - Receiving and monitoring a RedfishTask from the update

NOTE: SimpleUpdate issues an actual firmware update command.  Use the
      simulator or a non-production BMC to avoid unintended side-effects.
      Pass --dry-run to skip the actual update call.

Usage:
    python 10_update_service.py [--host HOST] [--port PORT] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.errors import RedfishConnectionError, RedfishTaskFailedError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 10 — Update Service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    p.add_argument(
        "--image-uri",
        default="http://fileserver.example.com/firmware.bin",
        help="URI of the firmware image for SimpleUpdate",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the actual SimpleUpdate call",
    )
    return p.parse_args()


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
        update = ctx.update

        # ── Firmware inventory ───────────────────────────────────────────
        print("Firmware inventory:")
        fw_resp = await update.list_firmware_inventory_async()
        if fw_resp.success:
            members = fw_resp.body.get("Members", [])
            print(f"  Items: {len(members)}")
            for item in members:
                uri = item.get("@odata.id", "")
                detail = await ctx.get_async(uri)
                if detail.success:
                    b = detail.body
                    print(
                        f"    {b.get('Id','?'):<20} "
                        f"{b.get('Name',''):<30} "
                        f"v{b.get('Version','?')}"
                    )
        else:
            print(f"  ✗ HTTP {fw_resp.status_code}")

        # ── Software inventory ───────────────────────────────────────────
        print("\nSoftware inventory:")
        sw_resp = await update.list_software_inventory_async()
        if sw_resp.success:
            members = sw_resp.body.get("Members", [])
            print(f"  Items: {len(members)}")
            for item in members:
                uri = item.get("@odata.id", "")
                detail = await ctx.get_async(uri)
                if detail.success:
                    b = detail.body
                    print(
                        f"    {b.get('Id','?'):<20} "
                        f"{b.get('Name',''):<30} "
                        f"v{b.get('Version','?')}"
                    )
        else:
            print(f"  ✗ HTTP {sw_resp.status_code}")

        # ── UpdateTargets — collect first FW target ──────────────────────
        target_uri: str | None = None
        if fw_resp.success:
            members = fw_resp.body.get("Members", [])
            if members:
                target_uri = members[0].get("@odata.id")

        # ── SimpleUpdate ─────────────────────────────────────────────────
        if args.dry_run:
            print("\n[DRY RUN] Skipping SimpleUpdate call")
        else:
            targets = [target_uri] if target_uri else []
            print(f"\nCalling SimpleUpdate:")
            print(f"  ImageURI  : {args.image_uri}")
            print(f"  Targets   : {targets}")
            print(f"  ApplyTime : Immediate")

            try:
                task = await update.simple_update_async(
                    image_uri=args.image_uri,
                    targets=targets,
                    transfer_protocol="HTTP",
                    apply_time="Immediate",
                )

                if task is None:
                    print("  ✓ Update completed synchronously (200/204)")
                else:
                    print(f"  ✓ Task created: {task.task_uri}")
                    print(f"  Task state    : {task.state}")

                    # Monitor with progress
                    print("  Monitoring task (30s timeout) …")
                    try:
                        async for snapshot in task.monitor_async():
                            pct = snapshot.percent_complete or 0
                            state = snapshot.state
                            print(f"    {state:<20} {pct}%")
                    except RedfishTaskFailedError as exc:
                        print(f"  ✗ Task failed: {exc.task.state}")
                    else:
                        print(f"  ✓ Task finished: {task.state}")

            except Exception as exc:  # noqa: BLE001
                print(f"  ✗ SimpleUpdate error: {exc}")
                print("    (Simulator may not implement SimpleUpdate)")

        print("\n✓ Update service sample complete")


if __name__ == "__main__":
    asyncio.run(main())
