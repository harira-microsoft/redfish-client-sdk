"""
Sample 15 — Multipart firmware upload via MockHttpClient (FR7.5)

Demonstrates UpdateServiceHandle.push_firmware_async() using the
MockHttpClient test double so no real BMC is needed.

Shows:
  - Wiring a MockHttpClient into UpdateServiceHandle directly
  - push_firmware() returning a 202 + Task URI
  - push_firmware() raising RedfishProtocolError when no push URI is present

Run:
  cd python
  python samples/15_multipart_upload.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redfish_sdk import MockHttpClient, RawHttpResponse
from redfish_sdk.models.redfish_types import AuthMode, AuthState, Credentials, TimeoutConfig
from redfish_sdk.services.update_service import UpdateServiceHandle
from redfish_sdk.errors import RedfishProtocolError


def _ok(body: dict) -> RawHttpResponse:
    import json
    return RawHttpResponse(200, {"content-type": "application/json"}, json.dumps(body), body)


def _accepted(task_uri: str) -> RawHttpResponse:
    return RawHttpResponse(202, {"location": task_uri}, "", {})


def _make_update_service(mock: MockHttpClient) -> UpdateServiceHandle:
    auth_state = AuthState(
        mode=AuthMode.STATELESS,
        credentials=Credentials("admin", "password"),
    )
    return UpdateServiceHandle(
        http=mock,
        auth_state=auth_state,
        discovery_map={},
        timeouts=TimeoutConfig(),
    )


def demo_successful_upload() -> None:
    print("=== Scenario 1: successful 202 multipart upload ===")

    mock = MockHttpClient({
        ("GET", "/redfish/v1/UpdateService"): _ok({
            "@odata.id": "/redfish/v1/UpdateService",
            "Name": "Update Service",
            "MultipartHttpPushUri": "/redfish/v1/UpdateService/upload",
        }),
        ("POST", "/redfish/v1/UpdateService/upload"): _accepted(
            "/redfish/v1/TaskService/Tasks/42"
        ),
    })

    svc = _make_update_service(mock)

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(b"\xDE\xAD\xBE\xEF" * 256)   # dummy 1 KB firmware image
        firmware_path = tmp.name

    try:
        resp = svc.push_firmware(
            local_path=firmware_path,
            targets=["/redfish/v1/Systems/1/Bios"],
            apply_time="OnReset",
        )
        print(f"  HTTP status  : {resp.status_code}")
        print(f"  Task attached: {resp.task is not None}")
        if resp.task:
            print(f"  Task URI     : {resp.task.task_uri}")
    finally:
        os.unlink(firmware_path)


def demo_no_push_uri() -> None:
    print("\n=== Scenario 2: UpdateService has no push URI ===")

    mock = MockHttpClient({
        ("GET", "/redfish/v1/UpdateService"): _ok({
            "@odata.id": "/redfish/v1/UpdateService",
            "Name": "Update Service",
            # deliberately no MultipartHttpPushUri / HttpPushUri
        }),
    })

    svc = _make_update_service(mock)

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(b"\x00" * 64)
        firmware_path = tmp.name

    try:
        try:
            svc.push_firmware(local_path=firmware_path)
            print("  UNEXPECTEDLY succeeded")
        except RedfishProtocolError as exc:
            print(f"  Correctly raised RedfishProtocolError: {exc}")
    finally:
        os.unlink(firmware_path)


def main() -> None:
    demo_successful_upload()
    demo_no_push_uri()
    print("\nDone.")


if __name__ == "__main__":
    main()
