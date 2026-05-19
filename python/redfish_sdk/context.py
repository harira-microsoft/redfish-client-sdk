# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/context.py

ClientContext — the opaque handle returned by connect().
All SDK operations go through this object.
Imports: discovery, services, protocol, transport.
"""

from __future__ import annotations

import asyncio
from typing import Any

from redfish_sdk.models.redfish_types import (
    AuthState,
    ConnectionConfig,
    EndpointCapabilities,
    TimeoutConfig,
)
from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.protocol.registry import MessageRegistry
import logging

from redfish_sdk.transport.auth import AuthManager
from redfish_sdk.transport.http_client import HttpClient

logger = logging.getLogger(__name__)


class ClientContext:
    """
    Opaque connection handle. Do not instantiate directly.
    Use redfish_sdk.connect() or redfish_sdk.connect_async().
    """

    def __init__(
        self,
        http: HttpClient,
        auth_state: AuthState,
        capabilities: EndpointCapabilities,
        config: ConnectionConfig,
        timeouts: TimeoutConfig,
    ) -> None:
        self._http = http
        self._auth_state = auth_state
        self._capabilities = capabilities
        self._config = config
        self._timeouts = timeouts
        self._discovery_map: dict[str, str] = {}
        self._schema_cache: dict[str, dict] = {}
        self._service_handles: dict[str, Any] = {}
        self._registry = MessageRegistry(http, auth_state)
        self._connected = True

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def base_url(self) -> str:
        return str(self._http._base_url)

    @property
    def capabilities(self) -> EndpointCapabilities:
        return self._capabilities

    # ------------------------------------------------------------------
    # Service handles (lazy) — canonical names
    # ------------------------------------------------------------------

    @property
    def event_service(self):
        from redfish_sdk.services.event_service import EventServiceHandle
        if "event_service" not in self._service_handles:
            self._service_handles["event_service"] = EventServiceHandle(
                self._http, self._auth_state, self._discovery_map
            )
        return self._service_handles["event_service"]

    @property
    def log_service(self):
        from redfish_sdk.services.log_service import LogServiceHandle
        if "log_service" not in self._service_handles:
            self._service_handles["log_service"] = LogServiceHandle(
                self._http, self._auth_state, self._discovery_map
            )
        return self._service_handles["log_service"]

    @property
    def telemetry_service(self):
        from redfish_sdk.services.telemetry_service import TelemetryServiceHandle
        if "telemetry_service" not in self._service_handles:
            self._service_handles["telemetry_service"] = TelemetryServiceHandle(
                self._http, self._auth_state, self._discovery_map
            )
        return self._service_handles["telemetry_service"]

    @property
    def update_service(self):
        from redfish_sdk.services.update_service import UpdateServiceHandle
        if "update_service" not in self._service_handles:
            self._service_handles["update_service"] = UpdateServiceHandle(
                self._http, self._auth_state, self._discovery_map, self._timeouts
            )
        return self._service_handles["update_service"]

    @property
    def ras_service(self):
        from redfish_sdk.services.ras_service import RasServiceHandle
        if "ras_service" not in self._service_handles:
            self._service_handles["ras_service"] = RasServiceHandle(
                self._http, self._auth_state, self._discovery_map
            )
        return self._service_handles["ras_service"]

    @property
    def discovery(self):
        from redfish_sdk.discovery.discovery import Discovery
        if "discovery" not in self._service_handles:
            self._service_handles["discovery"] = Discovery(
                self._http, self._auth_state, self._discovery_map, self._capabilities
            )
        return self._service_handles["discovery"]

    # ------------------------------------------------------------------
    # Short aliases used by samples
    # ------------------------------------------------------------------

    @property
    def events(self):
        return self.event_service

    @property
    def logs(self):
        return self.log_service

    @property
    def telemetry(self):
        return self.telemetry_service

    @property
    def update(self):
        return self.update_service

    @property
    def ras(self):
        return self.ras_service

    # ------------------------------------------------------------------
    # Discovery convenience methods
    # ------------------------------------------------------------------

    async def discover_async(self, service: str | None = None, root_only: bool = False):
        """Convenience wrapper: run discovery and return DiscoveryResult."""
        d = self.discovery
        if root_only:
            return await d.root_async()
        if service:
            return await d.partial_async(service)
        return await d.full_async()

    def discover(self, service: str | None = None, root_only: bool = False):
        import asyncio
        return asyncio.run(self.discover_async(service=service, root_only=root_only))


    async def get_async(self, uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    async def post_async(self, uri: str, body: dict) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", uri, headers=headers, body=body)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    async def patch_async(self, uri: str, body: dict) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("PATCH", uri, headers=headers, body=body)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    async def delete_async(self, uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("DELETE", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    # ------------------------------------------------------------------
    # Direct / raw access — sync
    # ------------------------------------------------------------------

    def get(self, uri: str) -> RedfishResponse:
        return asyncio.run(self.get_async(uri))

    def post(self, uri: str, body: dict) -> RedfishResponse:
        return asyncio.run(self.post_async(uri, body))

    def patch(self, uri: str, body: dict) -> RedfishResponse:
        return asyncio.run(self.patch_async(uri, body))

    def delete(self, uri: str) -> RedfishResponse:
        return asyncio.run(self.delete_async(uri))

    # ------------------------------------------------------------------    # Auth refresh — FR1.10
    # -----------------------------------------------------------------------

    async def refresh_auth_async(self) -> None:
        """Re-run the auth flow in-place without creating a new connection.

        Useful for token rotation (e.g. 72-hour session renewal). The
        existing ``ClientContext`` handle remains valid after the call.
        """
        logger.debug("refresh_auth: re-authenticating via %s", self._auth_state.mode.value)
        creds = self._auth_state.credentials or _dummy_creds()
        auth_manager = AuthManager(self._http, creds, self._auth_state.mode)
        self._auth_state = await auth_manager.authenticate_async()
        # Invalidate cached registry (holds a reference to auth_state)
        self._registry = type(self._registry)(self._http, self._auth_state)
        logger.debug("refresh_auth: done")

    def refresh_auth(self) -> None:
        """Sync wrapper for :meth:`refresh_auth_async`."""
        asyncio.run(self.refresh_auth_async())

    # -----------------------------------------------------------------------    # Lifecycle
    # ------------------------------------------------------------------

    async def close_async(self) -> None:
        if not self._connected:
            return
        logger.debug("Closing connection to %s", self.base_url)
        auth_manager = AuthManager(self._http, self._auth_state.credentials or _dummy_creds(), self._auth_state.mode)  # type: ignore[arg-type]
        await auth_manager.logout_async(self._auth_state)
        await self._http.close_async()
        self._connected = False
        logger.debug("Connection closed")

    def close(self) -> None:
        asyncio.run(self.close_async())

    async def __aenter__(self) -> "ClientContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_async()

    def __enter__(self) -> "ClientContext":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"ClientContext(base_url={self.base_url!r}, connected={self._connected})"


def _dummy_creds():
    from redfish_sdk.models.redfish_types import Credentials
    return Credentials(username="", password="")
