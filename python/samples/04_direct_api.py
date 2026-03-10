# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

#!/usr/bin/env python3
"""Sample 04 — Raw HTTP operations via ClientContext.

Demonstrates:
  - ctx.get_async()     — retrieve any resource
  - ctx.patch_async()   — modify a resource property
  - ctx.post_async()    — invoke an action
  - ctx.delete_async()  — remove a resource
  - Inspecting RedfishResponse (status_code, success, body, extended_info)

Usage:
    python 04_direct_api.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.errors import RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 04 — Direct API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    return p.parse_args()


def _dump(label: str, resp) -> None:
    status_icon = "✓" if resp.success else "✗"
    print(f"\n{status_icon} [{resp.status_code}] {label}")
    if resp.body:
        # Print only top-level keys to keep output readable
        top = {k: v for k, v in resp.body.items() if not k.startswith("@")}
        print(f"   body keys : {list(top.keys())[:10]}")
    if resp.extended_info:
        for msg in resp.extended_info:
            print(f"   message   : [{msg.severity}] {msg.message}")


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
        # ── GET /redfish/v1 ─────────────────────────────────────────────
        root = await ctx.get_async("/redfish/v1")
        _dump("GET /redfish/v1", root)
        if root.success:
            print(f"   RedfishVersion : {root.body.get('RedfishVersion')}")
            print(f"   UUID           : {root.body.get('UUID')}")

        # ── GET non-existent resource (expect 404, not exception) ───────
        missing = await ctx.get_async("/redfish/v1/DoesNotExist")
        _dump("GET /redfish/v1/DoesNotExist (expect 404)", missing)

        # ── GET Systems collection then first member ─────────────────────
        systems = await ctx.get_async("/redfish/v1/Systems")
        _dump("GET /redfish/v1/Systems", systems)

        first_sys_uri = None
        if systems.success:
            members = systems.body.get("Members", [])
            if members:
                first_sys_uri = members[0]["@odata.id"]

        # ── PATCH — set AssetTag on first system ────────────────────────
        if first_sys_uri:
            try:
                patch_resp = await ctx.patch_async(
                    first_sys_uri,
                    body={"AssetTag": "RSDK-Sample-04"},
                )
                _dump(f"PATCH {first_sys_uri} AssetTag", patch_resp)
            except Exception as exc:  # noqa: BLE001
                print(f"\n✗ PATCH {first_sys_uri} → {type(exc).__name__}: {exc} (simulator may not support PATCH)")
                first_sys_uri = None  # skip verify step

        # ── GET — verify PATCH took effect ──────────────────────────────
        if first_sys_uri:
            verify = await ctx.get_async(first_sys_uri)
            _dump(f"GET {first_sys_uri} (verify AssetTag)", verify)
            if verify.success:
                print(f"   AssetTag : {verify.body.get('AssetTag')}")

        # ── POST — Reset action on first system ─────────────────────────
        if first_sys_uri:
            reset_uri = f"{first_sys_uri}/Actions/ComputerSystem.Reset"
            try:
                reset_resp = await ctx.post_async(
                    reset_uri,
                    body={"ResetType": "GracefulRestart"},
                )
                _dump(f"POST {reset_uri}", reset_resp)
                if reset_resp.task:
                    print(f"   Task URI : {reset_resp.task.task_uri}")
            except Exception as exc:  # noqa: BLE001
                print(f"\n✗ POST {reset_uri} → {type(exc).__name__}: {exc} (simulator may not support this action)")

        print("\n✓ Direct API sample complete")


if __name__ == "__main__":
    asyncio.run(main())
