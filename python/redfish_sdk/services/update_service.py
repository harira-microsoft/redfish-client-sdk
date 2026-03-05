"""
redfish_sdk/services/update_service.py

UpdateService handle — firmware/software inventory, simple update.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.protocol.task import RedfishTask
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState, TimeoutConfig

_DEFAULT_SERVICE_PATH = "/redfish/v1/UpdateService"


class UpdateServiceHandle:

    def __init__(
        self,
        http: HttpClient,
        auth_state: AuthState,
        discovery_map: dict[str, str],
        timeouts: TimeoutConfig,
    ) -> None:
        self._http = http
        self._auth_state = auth_state
        self._discovery_map = discovery_map
        self._timeouts = timeouts

    @property
    def _service_uri(self) -> str:
        return self._discovery_map.get("UpdateService", _DEFAULT_SERVICE_PATH)

    # ------------------------------------------------------------------
    # Service info
    # ------------------------------------------------------------------

    async def get_service_info_async(self) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", self._service_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_service_info(self) -> RedfishResponse:
        return asyncio.run(self.get_service_info_async())

    # ------------------------------------------------------------------
    # Firmware Inventory
    # ------------------------------------------------------------------

    async def list_firmware_inventory_async(self) -> RedfishResponse:
        uri = f"{self._service_uri}/FirmwareInventory"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_firmware_inventory(self) -> RedfishResponse:
        return asyncio.run(self.list_firmware_inventory_async())

    async def get_firmware_component_async(self, component_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", component_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_firmware_component(self, component_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_firmware_component_async(component_uri))

    # ------------------------------------------------------------------
    # Software Inventory
    # ------------------------------------------------------------------

    async def list_software_inventory_async(self) -> RedfishResponse:
        uri = f"{self._service_uri}/SoftwareInventory"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_software_inventory(self) -> RedfishResponse:
        return asyncio.run(self.list_software_inventory_async())

    async def get_software_component_async(self, component_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", component_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_software_component(self, component_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_software_component_async(component_uri))

    # ------------------------------------------------------------------
    # Simple Update
    # ------------------------------------------------------------------

    async def simple_update_async(
        self,
        image_uri: str,
        targets: list[str] | None = None,
        transfer_protocol: str | None = None,
        apply_time: str | None = None,
    ) -> RedfishResponse:
        body: dict = {"ImageURI": image_uri}
        if targets:
            body["Targets"] = targets
        if transfer_protocol:
            body["TransferProtocol"] = transfer_protocol
        if apply_time:
            body["@Redfish.OperationApplyTime"] = apply_time

        action_uri = f"{self._service_uri}/Actions/UpdateService.SimpleUpdate"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", action_uri, headers=headers, body=body)

        task: RedfishTask | None = None
        if raw.status_code == 202:
            task_uri = (raw.headers.get("location") or raw.headers.get("Location") or "")
            if not task_uri and isinstance(raw.body_json, dict):
                task_uri = raw.body_json.get("@odata.id", "")
            if task_uri:
                task = RedfishTask(task_uri=task_uri)
                task._bind(self._http, self._auth_state, self._timeouts)

        return build_response(
            raw.status_code, raw.headers, raw.body_json, raw.body_text, task=task
        )

    def simple_update(
        self,
        image_uri: str,
        targets: list[str] | None = None,
        transfer_protocol: str | None = None,
        apply_time: str | None = None,
    ) -> RedfishResponse:
        return asyncio.run(
            self.simple_update_async(image_uri, targets, transfer_protocol, apply_time)
        )
