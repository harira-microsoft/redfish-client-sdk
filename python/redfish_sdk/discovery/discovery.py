"""
redfish_sdk/discovery/discovery.py

Traverses the Redfish service tree and reports what is available.
Updates the context's _discovery_map as a side effect.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from redfish_sdk.transport.auth import AuthManager
from redfish_sdk.models.redfish_types import EndpointCapabilities

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

# Top-level Redfish service keys we care about
_SERVICE_KEYS = [
    "EventService",
    "LogService",
    "TelemetryService",
    "UpdateService",
    "SessionService",
    "AccountService",
    "TaskService",
    "Systems",
    "Chassis",
    "Managers",
]


@dataclass
class DiscoveryResult:
    services: dict[str, str] = field(default_factory=dict)     # name → URI
    capabilities: EndpointCapabilities = field(default_factory=EndpointCapabilities)
    raw: dict = field(default_factory=dict)

    def has_service(self, name: str) -> bool:
        return name in self.services

    def service_uri(self, name: str) -> str | None:
        return self.services.get(name)


class Discovery:

    def __init__(
        self,
        http: HttpClient,
        auth_state: AuthState,
        discovery_map: dict[str, str],
        capabilities: EndpointCapabilities | None = None,
    ) -> None:
        self._http = http
        self._auth_state = auth_state
        self._map = discovery_map   # reference to context's map — side effect updates it
        self._capabilities = capabilities or EndpointCapabilities()

    # ------------------------------------------------------------------
    # Public — async
    # ------------------------------------------------------------------

    async def full_async(self) -> DiscoveryResult:
        service_root = await self._get_service_root_async()
        services: dict[str, str] = {}
        for key in _SERVICE_KEYS:
            if key in service_root:
                uri = service_root[key].get("@odata.id", "")
                if uri:
                    services[key] = uri
        self._map.update(services)
        return DiscoveryResult(
            services=services,
            capabilities=self._capabilities,
            raw=service_root,
        )

    async def partial_async(self, service: str) -> DiscoveryResult:
        service_root = await self._get_service_root_async()
        services: dict[str, str] = {}
        if service in service_root:
            uri = service_root[service].get("@odata.id", "")
            if uri:
                services[service] = uri
        self._map.update(services)
        return DiscoveryResult(
            services=services,
            capabilities=self._capabilities,
            raw=service_root,
        )

    async def root_async(self) -> DiscoveryResult:
        service_root = await self._get_service_root_async()
        # Root mode: enumerate keys without traversal
        services = {
            k: service_root[k].get("@odata.id", "")
            for k in _SERVICE_KEYS
            if k in service_root and isinstance(service_root[k], dict)
        }
        services = {k: v for k, v in services.items() if v}
        return DiscoveryResult(
            services=services,
            capabilities=self._capabilities,
            raw=service_root,
        )

    # ------------------------------------------------------------------
    # Public — sync
    # ------------------------------------------------------------------

    def full(self) -> DiscoveryResult:
        return asyncio.run(self.full_async())

    def partial(self, service: str) -> DiscoveryResult:
        return asyncio.run(self.partial_async(service))

    def root(self) -> DiscoveryResult:
        return asyncio.run(self.root_async())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_service_root_async(self) -> dict:
        from redfish_sdk.errors import RedfishProtocolError
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", "/redfish/v1", headers=headers)
        if raw.status_code != 200 or not isinstance(raw.body_json, dict):
            raise RedfishProtocolError(
                f"Failed to fetch ServiceRoot — HTTP {raw.status_code}"
            )
        return raw.body_json
