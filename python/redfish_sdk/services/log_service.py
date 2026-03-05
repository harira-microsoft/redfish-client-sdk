"""
redfish_sdk/services/log_service.py

LogService handle — list services, get/filter entries, clear log.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

_DEFAULT_SERVICE_PATH = "/redfish/v1/Systems/1/LogServices"


@dataclass
class LogFilter:
    severity: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    message_id: str | None = None
    max_entries: int | None = None


class LogServiceHandle:

    def __init__(
        self,
        http: HttpClient,
        auth_state: AuthState,
        discovery_map: dict[str, str],
    ) -> None:
        self._http = http
        self._auth_state = auth_state
        self._discovery_map = discovery_map

    @property
    def _service_uri(self) -> str:
        return self._discovery_map.get("LogService", _DEFAULT_SERVICE_PATH)

    # ------------------------------------------------------------------
    # List services
    # ------------------------------------------------------------------

    async def list_services_async(self) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", self._service_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_services(self) -> RedfishResponse:
        return asyncio.run(self.list_services_async())

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    async def get_entries_async(
        self,
        log_service_uri: str,
        filter: LogFilter | None = None,
    ) -> RedfishResponse:
        entries_uri = f"{log_service_uri.rstrip('/')}/Entries"
        query_params = _build_filter_params(filter)
        if query_params:
            entries_uri = f"{entries_uri}?{query_params}"

        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", entries_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_entries(
        self,
        log_service_uri: str,
        filter: LogFilter | None = None,
    ) -> RedfishResponse:
        return asyncio.run(self.get_entries_async(log_service_uri, filter))

    async def get_entry_async(self, entry_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", entry_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_entry(self, entry_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_entry_async(entry_uri))

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    async def clear_log_async(self, log_service_uri: str) -> RedfishResponse:
        clear_uri = f"{log_service_uri.rstrip('/')}/Actions/LogService.ClearLog"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", clear_uri, headers=headers, body={})
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def clear_log(self, log_service_uri: str) -> RedfishResponse:
        return asyncio.run(self.clear_log_async(log_service_uri))


def _build_filter_params(filter: LogFilter | None) -> str:
    if not filter:
        return ""
    parts = []
    if filter.severity:
        parts.append(f"$filter=Severity eq '{filter.severity}'")
    if filter.max_entries:
        parts.append(f"$top={filter.max_entries}")
    return "&".join(parts)
