# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/protocol/registry.py

Fetches DMTF Message Registry files from the BMC and decodes MessageId
strings into human-readable RedfishMessage objects.

Cache lives for the lifetime of the object (held in ClientContext).
Imports: transport, models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redfish_sdk.protocol.response import RedfishMessage

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState


class MessageRegistry:

    def __init__(self, http: HttpClient, auth_state: AuthState) -> None:
        self._http = http
        self._auth_state = auth_state
        self._cache: dict[str, dict] = {}   # registry prefix → registry JSON

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    async def resolve_async(self, message_id: str) -> RedfishMessage | None:
        parts = message_id.split(".")
        if len(parts) < 4:
            return None
        prefix = parts[0]
        key = parts[-1]

        registry = await self._get_registry_async(prefix)
        if not registry:
            return None
        return self._build_message(message_id, key, registry)

    def resolve(self, message_id: str) -> RedfishMessage | None:
        import asyncio
        return asyncio.run(self.resolve_async(message_id))

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch_async(self, registry_prefix: str) -> bool:
        registry = await self._get_registry_async(registry_prefix)
        return registry is not None

    def fetch(self, registry_prefix: str) -> bool:
        import asyncio
        return asyncio.run(self.fetch_async(registry_prefix))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_registry_async(self, prefix: str) -> dict | None:
        if prefix in self._cache:
            return self._cache[prefix]

        from redfish_sdk.transport.auth import AuthManager
        headers = AuthManager.attach_auth(self._auth_state, {})

        # Try the standard Redfish registry path
        path = f"/redfish/v1/Registries/{prefix}/{prefix}.json"
        raw = await self._http.request_async("GET", path, headers=headers)
        if raw.status_code == 200 and isinstance(raw.body_json, dict):
            self._cache[prefix] = raw.body_json
            return raw.body_json

        return None

    @staticmethod
    def _build_message(message_id: str, key: str, registry: dict) -> RedfishMessage | None:
        messages: dict = registry.get("Messages", {})
        entry = messages.get(key)
        if not entry:
            return None
        return RedfishMessage(
            message_id=message_id,
            message=entry.get("Message", ""),
            severity=entry.get("Severity", "OK"),
            resolution=entry.get("Resolution"),
            message_args=[],
        )
