# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

#!/usr/bin/env python3
"""Sample 05 — EventService subscriptions (subscribe / list / delete).

Demonstrates:
  - ctx.events.subscribe_async()
  - ctx.events.list_subscriptions_async()
  - ctx.events.get_subscription_async()
  - ctx.events.delete_subscription_async()
  - ctx.events.submit_test_event_async()

NOTE: This sample only manages subscriptions; it does not start a local
      listener.  For end-to-end event delivery see sample 06.

Usage:
    python 05_event_subscribe.py [--host HOST] [--port PORT]
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
    p = argparse.ArgumentParser(description="Sample 05 — Event Subscriptions")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    p.add_argument(
        "--destination",
        default="http://YOUR_LISTENER_HOST:9090/events",
        help="HTTP destination URL for the subscription",
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
        events = ctx.events

        # ── Create subscription ─────────────────────────────────────────
        print(f"Creating subscription → {args.destination}")
        sub_resp = await events.subscribe_async(
            destination=args.destination,
            event_types=["Alert", "ResourceUpdated", "StatusChange"],
            context="RSDK-Sample-05",
            protocol="Redfish",
        )

        if sub_resp.success:
            sub_uri = sub_resp.headers.get("Location") or sub_resp.body.get("@odata.id", "")
            print(f"  ✓ Subscribed — URI: {sub_uri}")
        else:
            print(f"  ✗ Subscribe failed: HTTP {sub_resp.status_code}")
            sub_uri = None

        # ── List subscriptions ──────────────────────────────────────────
        print("\nListing all subscriptions …")
        list_resp = await events.list_subscriptions_async()
        if list_resp.success:
            members = list_resp.body.get("Members", [])
            print(f"  Total: {len(members)}")
            for m in members:
                print(f"    {m.get('@odata.id')}")
        else:
            print(f"  ✗ List failed: HTTP {list_resp.status_code}")

        # ── Get single subscription ─────────────────────────────────────
        if sub_uri:
            print(f"\nFetching subscription detail: {sub_uri}")
            get_resp = await events.get_subscription_async(sub_uri)
            if get_resp.success:
                body = get_resp.body
                print(f"  Destination : {body.get('Destination')}")
                print(f"  Context     : {body.get('Context')}")
                print(f"  EventTypes  : {body.get('EventTypes')}")
                print(f"  Protocol    : {body.get('Protocol')}")

        # ── Submit test event ───────────────────────────────────────────
        print("\nSubmitting test event …")
        test_resp = await events.submit_test_event_async()
        if test_resp.success:
            print("  ✓ Test event submitted")
        else:
            # Many simulators do not implement SubmitTestEvent — that is OK
            print(f"  ✗ HTTP {test_resp.status_code} (may not be supported)")

        # ── Delete subscription ─────────────────────────────────────────
        if sub_uri:
            print(f"\nDeleting subscription: {sub_uri}")
            del_resp = await events.delete_subscription_async(sub_uri)
            if del_resp.success:
                print("  ✓ Deleted")
            else:
                print(f"  ✗ Delete failed: HTTP {del_resp.status_code}")

        print("\n✓ Event subscription sample complete")


if __name__ == "__main__":
    asyncio.run(main())
