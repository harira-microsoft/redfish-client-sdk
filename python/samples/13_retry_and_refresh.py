# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
Sample 13 — Retry config and session refresh (FR1.8, FR1.9, FR1.10)

Demonstrates:
  - ConnectionConfig with retry_on_connection_failure and retry_status_codes
  - ctx.refresh_auth() — re-runs the auth flow without a new TCP connection

Run:
  cd python
  python samples/13_retry_and_refresh.py
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Enable SDK debug logging so retry/refresh messages are visible
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

import redfish_sdk
from redfish_sdk import (
    connect,
    Credentials,
    AuthMode,
    ConnectionConfig,
)


def main() -> None:
    creds = Credentials(username="admin", password="password")

    # --- FR1.8 / FR1.9: retry configuration ---
    cfg = ConnectionConfig(
        verify_tls=False,
        retry_on_connection_failure=2,      # up to 2 extra attempts on ConnectError
        retry_status_codes=[503, 429],      # also retry on these HTTP status codes
        retry_delay_sec=1.0,                # 1 s between attempts
    )

    print("Connecting with retry config (retry=2, status_codes=[503, 429]) …")
    ctx = connect(
        host="127.0.0.1",
        port=8000,
        credentials=creds,
        auth_mode=AuthMode.STATELESS,
        config=cfg,
    )
    print(f"Connected: {ctx}")
    print(f"  Redfish version : {ctx.capabilities.redfish_version}")

    # --- FR1.10: in-place session refresh ---
    print("\nRefreshing auth (simulates token rotation) …")
    ctx.refresh_auth()
    print("  Auth refreshed — context handle is still valid")

    # Verify the context still works after refresh
    root = ctx.get("/redfish/v1")
    print(f"  GET /redfish/v1 after refresh → HTTP {root.status_code}")
    assert root.status_code == 200, "Expected 200 after refresh"

    ctx.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
