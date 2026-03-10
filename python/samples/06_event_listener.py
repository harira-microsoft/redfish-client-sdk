# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

#!/usr/bin/env python3
"""Sample 06 — Start embedded RedfishEventListener and auto-subscribe.

Demonstrates:
  - RedfishEventListener instantiation
  - listener.use_context(ctx)
  - listener.on_event() global callback
  - listener.start() / listener.stop()
  - Auto-subscribe with listener.listen_url as destination
  - Waiting for test events with a timeout

The listener binds on the local machine; the subscription destination is
set to the listener URL so the BMC (or simulator) POSTs events here.

Usage:
    python 06_event_listener.py [--host HOST] [--port PORT]
                                [--listen-host LISTEN_HOST]
                                [--listen-port LISTEN_PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials, RedfishEventListener
from redfish_sdk.services.event_service import RedfishEvent
from redfish_sdk.errors import RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 06 — Event Listener")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    p.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Interface the listener binds to",
    )
    p.add_argument(
        "--listen-port",
        type=int,
        default=9090,
        help="Port the listener binds to",
    )
    p.add_argument(
        "--wait",
        type=float,
        default=10.0,
        help="Seconds to wait for events before exiting",
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
        # ── Build and start listener ────────────────────────────────────
        listener = RedfishEventListener(
            port=args.listen_port,
            host=args.listen_host,
        )
        listener.use_context(ctx)

        received: list[RedfishEvent] = []

        @listener.on_event
        async def on_any_event(event: RedfishEvent) -> None:
            received.append(event)
            print(f"  [EVENT] type={event.event_type!r}  id={event.message_id!r}")
            print(f"          msg ={event.message!r}")
            print(f"          sev ={event.severity!r}")

        listener.start()
        print(f"✓ Listener running at {listener.listen_url}")

        # ── Subscribe ────────────────────────────────────────────────────
        # Use 127.0.0.1 as destination so simulator can reach us locally
        dest = f"http://127.0.0.1:{args.listen_port}/events"
        print(f"Subscribing → {dest}")

        sub_resp = await ctx.events.subscribe_async(
            destination=dest,
            event_types=["Alert", "ResourceUpdated", "StatusChange"],
            context="RSDK-Sample-06",
        )

        sub_uri: str | None = None
        if sub_resp.success:
            sub_uri = sub_resp.headers.get("Location") or sub_resp.body.get("@odata.id")
            print(f"  ✓ Subscribed — URI: {sub_uri}")
        else:
            print(f"  ✗ Subscribe failed HTTP {sub_resp.status_code}; still waiting for events")

        # ── Trigger a test event ─────────────────────────────────────────
        print("Submitting test event …")
        await ctx.events.submit_test_event_async()

        # ── Wait for events ──────────────────────────────────────────────
        print(f"Waiting up to {args.wait}s for incoming events …")
        await asyncio.sleep(args.wait)

        print(f"\nReceived {len(received)} event(s) in {args.wait}s")

        # ── Cleanup ──────────────────────────────────────────────────────
        if sub_uri:
            await ctx.events.delete_subscription_async(sub_uri)
            print("✓ Subscription deleted")

        listener.stop()
        print("✓ Listener stopped")

        print("\n✓ Event listener sample complete")


if __name__ == "__main__":
    asyncio.run(main())
