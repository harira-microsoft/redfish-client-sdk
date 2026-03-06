#!/usr/bin/env python3
"""Sample 07 — Event listener with type and registry-prefix filtering.

Demonstrates:
  - listener.on_event_type(event_type, callback)
  - listener.on_registry(registry_prefix, callback)
  - Combining multiple callback registrations
  - Async vs sync callbacks

Usage:
    python 07_event_monitor.py [--host HOST] [--port PORT]
                               [--listen-port LISTEN_PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials, RedfishEventListener
from redfish_sdk.services.event_service import RedfishEvent
from redfish_sdk.errors import RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 07 — Event Monitor")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    p.add_argument("--listen-port", type=int, default=9091)
    p.add_argument("--wait", type=float, default=15.0)
    return p.parse_args()


# ── Module-level counters (shared across callbacks) ──────────────────────────
_stats: dict[str, int] = {
    "total": 0,
    "alerts": 0,
    "base_registry": 0,
    "status_change": 0,
}


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
        listener = RedfishEventListener(port=args.listen_port)
        listener.use_context(ctx)

        # ── Global catch-all (sync) ──────────────────────────────────────
        def catch_all(event: RedfishEvent) -> None:
            _stats["total"] += 1
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [ALL      {ts}] {event.event_type} — {event.message_id}")

        listener.on_event(catch_all)

        # ── Alert-type filter (async) ────────────────────────────────────
        async def on_alert(event: RedfishEvent) -> None:
            _stats["alerts"] += 1
            print(f"  [ALERT   ] severity={event.severity!r}  msg={event.message!r}")

        listener.on_event_type("Alert", on_alert)

        # ── StatusChange filter (sync) ───────────────────────────────────
        def on_status_change(event: RedfishEvent) -> None:
            _stats["status_change"] += 1
            print(f"  [STATUS  ] origin={event.origin_of_condition!r}")

        listener.on_event_type("StatusChange", on_status_change)

        # ── "Base" registry filter (async) ───────────────────────────────
        async def on_base_registry(event: RedfishEvent) -> None:
            _stats["base_registry"] += 1
            print(f"  [BASE.REG] {event.message_id} — {event.message}")

        listener.on_registry("Base", on_base_registry)

        # ── Start ────────────────────────────────────────────────────────
        listener.start()
        print(f"✓ Listener active at {listener.listen_url}")
        print(f"  Callbacks: catch_all (all), Alert, StatusChange, Base.*\n")

        dest = f"http://127.0.0.1:{args.listen_port}/events"
        sub_resp = await ctx.events.subscribe_async(
            destination=dest,
            event_types=["Alert", "ResourceUpdated", "StatusChange"],
            context="RSDK-Sample-07",
        )

        sub_uri: str | None = None
        if sub_resp.success:
            sub_uri = sub_resp.headers.get("Location") or sub_resp.body.get("@odata.id")
            print(f"✓ Subscribed — {sub_uri}")
        else:
            print(f"✗ Subscribe HTTP {sub_resp.status_code}")

        # Trigger several test events
        for _ in range(3):
            await ctx.events.submit_test_event_async()
            await asyncio.sleep(0.5)

        print(f"\nWaiting {args.wait}s for events …")
        await asyncio.sleep(args.wait)

        # ── Stats ────────────────────────────────────────────────────────
        print("\n── Event statistics ──────────────────────")
        for key, val in _stats.items():
            print(f"  {key:<16}: {val}")

        # ── Cleanup ──────────────────────────────────────────────────────
        if sub_uri:
            await ctx.events.delete_subscription_async(sub_uri)
        listener.stop()

        print("\n✓ Event monitor sample complete")


if __name__ == "__main__":
    asyncio.run(main())
