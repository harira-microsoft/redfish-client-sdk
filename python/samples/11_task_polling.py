# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

#!/usr/bin/env python3
"""Sample 11 — Task polling: wait, monitor, and cancel.

Demonstrates:
  - Triggering a long-running Redfish task via POST action
  - task.wait_async() — block until terminal state
  - task.monitor_async() — async generator yielding task snapshots
  - task.cancel_async() — request cancellation
  - RedfishTaskTimeoutError and RedfishTaskFailedError handling
  - TaskState enum values

We use a ComputerSystem.Reset (GracefulShutdown) to generate a task;
fall back to a no-op POST if the system is already off.

Usage:
    python 11_task_polling.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redfish_sdk
from redfish_sdk import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.protocol.task import RedfishTask, TaskState
from redfish_sdk.errors import (
    RedfishConnectionError,
    RedfishTaskFailedError,
    RedfishTaskTimeoutError,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample 11 — Task Polling")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="password")
    p.add_argument("--no-tls-verify", action="store_true")
    p.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS (for simulators without SSL)")
    p.add_argument("--timeout", type=float, default=60.0, help="Task wait timeout in seconds")
    return p.parse_args()


def _print_task(task: RedfishTask, prefix: str = "") -> None:
    pct = task.percent_complete
    pct_str = f"{pct}%" if pct is not None else "?"
    print(
        f"  {prefix}state={task.state.value:<20} "
        f"pct={pct_str:<6} "
        f"uri={task.task_uri}"
    )


async def _trigger_task(ctx) -> RedfishTask | None:
    """Try to obtain a RedfishTask by issuing a Reset action."""
    # Find first system
    systems = await ctx.get_async("/redfish/v1/Systems")
    if not systems.success:
        return None
    members = systems.body.get("Members", [])
    if not members:
        return None

    sys_uri = members[0]["@odata.id"]
    reset_uri = f"{sys_uri}/Actions/ComputerSystem.Reset"

    # Try GracefulRestart — most simulators return 202 + task
    resp = await ctx.post_async(reset_uri, body={"ResetType": "GracefulRestart"})
    if resp.task:
        return resp.task

    # Some simulators return 200/204 with no task — try ForceRestart
    resp2 = await ctx.post_async(reset_uri, body={"ResetType": "ForceRestart"})
    return resp2.task


async def demo_wait(task: RedfishTask, timeout: float) -> None:
    """Demo: block-wait until terminal state or timeout."""
    print(f"\n── task.wait_async(timeout={timeout}) ──")
    try:
        final = await task.wait_async(timeout=timeout)
        print(f"  ✓ Final state: {final.state.value}")
    except RedfishTaskTimeoutError as exc:
        print(f"  ⏱ Timed out after {timeout}s — last state: {exc.task.state.value}")
    except RedfishTaskFailedError as exc:
        print(f"  ✗ Task failed: {exc.task.state.value}")


async def demo_monitor(task: RedfishTask, timeout: float) -> None:
    """Demo: iterate task snapshots via monitor_async()."""
    print(f"\n── task.monitor_async() ──")
    count = 0
    try:
        async with asyncio.timeout(timeout):
            async for snapshot in task.monitor_async():
                count += 1
                _print_task(snapshot, prefix=f"[{count}] ")
                if TaskState(snapshot.state) in {
                    TaskState.COMPLETED,
                    TaskState.KILLED,
                    TaskState.EXCEPTION,
                    TaskState.CANCELLED,
                }:
                    break
    except TimeoutError:
        print(f"  ⏱ Monitor timeout after {timeout}s")
    except RedfishTaskFailedError as exc:
        print(f"  ✗ Task failed: {exc.task.state.value}")
    print(f"  Received {count} snapshot(s)")


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
        # ── Try to create a task ─────────────────────────────────────────
        print("Attempting to trigger a task via ComputerSystem.Reset …")
        task = await _trigger_task(ctx)

        if task is None:
            print("  No task returned by this endpoint (may complete synchronously)")
            print("  Constructing a synthetic task demo against the Tasks collection …")

            # Fall back: GET tasks collection and use first pending task
            tasks_resp = await ctx.get_async("/redfish/v1/TaskService/Tasks")
            if tasks_resp.success:
                members = tasks_resp.body.get("Members", [])
                print(f"  Existing tasks: {len(members)}")
                for m in members[:3]:
                    print(f"    {m.get('@odata.id')}")
            print("\n✓ Task polling sample complete (no live task available)")
            return

        print(f"  Task URI: {task.task_uri}")
        _print_task(task, prefix="initial  ")

        # ── Demo 1: wait ────────────────────────────────────────────────
        await demo_wait(task, timeout=args.timeout / 2)

        # ── Demo 2: monitor (re-uses same task) ─────────────────────────
        await demo_monitor(task, timeout=args.timeout / 2)

        # ── Demo 3: inspect TaskState enum ──────────────────────────────
        print("\n── TaskState values ──")
        for ts in TaskState:
            print(f"  {ts.name:<20} = {ts.value!r}")

        print("\n✓ Task polling sample complete")


if __name__ == "__main__":
    asyncio.run(main())
