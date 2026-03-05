#!/usr/bin/env python3
"""Sample 12 — Session auth vs stateless Basic auth comparison.

Demonstrates:
  - AuthMode.SESSION  — POST to SessionService, receive X-Auth-Token
  - AuthMode.STATELESS — Basic auth on every request, no session cookie
  - Verifying both modes can read the same resources
  - Session lifecycle: create → use → logout (ctx.close_async)
  - Inspecting EndpointCapabilities from each connection

Usage:
    python 12_session_vs_stateless.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.errors import RedfishAuthError, RedfishConnectionError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 12 — Session vs Stateless")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    return p.parse_args()


async def run_session(host: str, port: int, creds: Credentials, config: ConnectionConfig) -> None:
    print("\n" + "═" * 60)
    print("  AuthMode.SESSION")
    print("═" * 60)

    try:
        t0 = time.perf_counter()
        ctx = await redfish_sdk.connect_async(
            host=host,
            port=port,
            credentials=creds,
            auth_mode=AuthMode.SESSION,
            config=config,
        )
        elapsed = time.perf_counter() - t0
        print(f"  ✓ Connected in {elapsed*1000:.1f}ms")
    except RedfishAuthError as exc:
        print(f"  ✗ Auth failed: {exc}")
        return
    except RedfishConnectionError as exc:
        print(f"  ✗ Connect failed: {exc}")
        return

    async with ctx:
        caps = ctx.capabilities
        print(f"  RedfishVersion : {caps.redfish_version}")
        print(f"  UUID           : {caps.uuid}")
        print(f"  SessionURI     : {caps.session_service_uri or 'N/A'}")

        # Verify we can read resources
        t0 = time.perf_counter()
        systems = await ctx.get_async("/redfish/v1/Systems")
        elapsed = time.perf_counter() - t0
        icon = "✓" if systems.success else "✗"
        print(f"  {icon} GET /redfish/v1/Systems → {systems.status_code}  ({elapsed*1000:.1f}ms)")

        # Multiple requests use the same session token
        for _ in range(3):
            t0 = time.perf_counter()
            r = await ctx.get_async("/redfish/v1")
            elapsed = time.perf_counter() - t0
            print(f"  ✓ GET /redfish/v1           → {r.status_code}  ({elapsed*1000:.1f}ms)")

        print("  (Session token reused across all requests)")
        # ctx.__aexit__ → ctx.close_async() → logout
    print("  ✓ Session closed (X-Auth-Token invalidated via logout)")


async def run_stateless(host: str, port: int, creds: Credentials, config: ConnectionConfig) -> None:
    print("\n" + "═" * 60)
    print("  AuthMode.STATELESS  (Basic auth per request)")
    print("═" * 60)

    try:
        t0 = time.perf_counter()
        ctx = await redfish_sdk.connect_async(
            host=host,
            port=port,
            credentials=creds,
            auth_mode=AuthMode.STATELESS,
            config=config,
        )
        elapsed = time.perf_counter() - t0
        print(f"  ✓ Connected in {elapsed*1000:.1f}ms")
    except RedfishAuthError as exc:
        print(f"  ✗ Auth failed: {exc}")
        return
    except RedfishConnectionError as exc:
        print(f"  ✗ Connect failed: {exc}")
        return

    async with ctx:
        caps = ctx.capabilities
        print(f"  RedfishVersion : {caps.redfish_version}")
        print(f"  UUID           : {caps.uuid}")

        # Verify same resources reachable
        t0 = time.perf_counter()
        systems = await ctx.get_async("/redfish/v1/Systems")
        elapsed = time.perf_counter() - t0
        icon = "✓" if systems.success else "✗"
        print(f"  {icon} GET /redfish/v1/Systems → {systems.status_code}  ({elapsed*1000:.1f}ms)")

        # Each request carries Authorization: Basic ...
        for _ in range(3):
            t0 = time.perf_counter()
            r = await ctx.get_async("/redfish/v1")
            elapsed = time.perf_counter() - t0
            print(f"  ✓ GET /redfish/v1           → {r.status_code}  ({elapsed*1000:.1f}ms)")

        print("  (Basic credentials re-sent on every request)")
    print("  ✓ Context closed (no session to invalidate)")


async def bad_credentials(host: str, port: int, config: ConnectionConfig) -> None:
    """Show how auth failures surface."""
    print("\n── Bad credentials demo ──")
    bad_creds = Credentials(username="wrong", password="wrong")
    try:
        ctx = await redfish_sdk.connect_async(
            host=host,
            port=port,
            credentials=bad_creds,
            auth_mode=AuthMode.SESSION,
            config=config,
        )
        await ctx.close_async()
        print("  (Endpoint accepted bad credentials — unusual)")
    except RedfishAuthError as exc:
        print(f"  ✓ RedfishAuthError raised as expected: {exc}")
    except RedfishConnectionError as exc:
        print(f"  ✓ Connection-level error: {exc}")


async def main() -> None:
    args = parse_args()

    creds = Credentials(username=args.user, password=args.password)
    config = ConnectionConfig(verify_tls=not args.no_tls_verify)

    await run_session(args.host, args.port, creds, config)
    await run_stateless(args.host, args.port, creds, config)
    await bad_credentials(args.host, args.port, config)

    print("\n✓ Session vs stateless comparison complete")


if __name__ == "__main__":
    asyncio.run(main())
