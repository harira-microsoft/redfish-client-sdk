"""
redfish_sdk/services/event_service.py

EventService handle — subscriptions, SSE streaming.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, AsyncGenerator

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

_DEFAULT_SERVICE_PATH = "/redfish/v1/EventService"


class RedfishEvent:
    __slots__ = (
        "event_id", "event_type", "event_timestamp",
        "message_id", "message", "severity",
        "origin_of_condition", "raw",
    )

    def __init__(
        self,
        event_id: str = "",
        event_type: str = "",
        event_timestamp: str = "",
        message_id: str = "",
        message: str = "",
        severity: str = "",
        origin_of_condition: str | None = None,
        raw: dict | None = None,
    ) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.event_timestamp = event_timestamp
        self.message_id = message_id
        self.message = message
        self.severity = severity
        self.origin_of_condition = origin_of_condition
        self.raw = raw or {}

    def __repr__(self) -> str:
        return (
            f"RedfishEvent(id={self.event_id!r}, type={self.event_type!r}, "
            f"message_id={self.message_id!r})"
        )


class EventServiceHandle:

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
        return self._discovery_map.get("EventService", _DEFAULT_SERVICE_PATH)

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
    # Subscriptions
    # ------------------------------------------------------------------

    async def subscribe_async(
        self,
        destination: str,
        event_types: list[str] | None = None,
        registry_prefixes: list[str] | None = None,
        message_ids: list[str] | None = None,
        context: str | None = None,
        protocol: str = "Redfish",
        subscription_type: str = "RedfishEvent",
    ) -> RedfishResponse:
        body: dict = {
            "Destination": destination,
            "Protocol": protocol,
            "SubscriptionType": subscription_type,
        }
        if event_types:
            body["EventTypes"] = event_types
        if registry_prefixes:
            body["RegistryPrefixes"] = registry_prefixes
        if message_ids:
            body["MessageIds"] = message_ids
        if context:
            body["Context"] = context

        subs_uri = f"{self._service_uri}/Subscriptions"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", subs_uri, headers=headers, body=body)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def subscribe(self, destination: str, **kwargs) -> RedfishResponse:
        return asyncio.run(self.subscribe_async(destination, **kwargs))

    async def list_subscriptions_async(self) -> RedfishResponse:
        subs_uri = f"{self._service_uri}/Subscriptions"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", subs_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_subscriptions(self) -> RedfishResponse:
        return asyncio.run(self.list_subscriptions_async())

    async def get_subscription_async(self, subscription_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", subscription_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_subscription(self, subscription_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_subscription_async(subscription_uri))

    async def delete_subscription_async(self, subscription_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("DELETE", subscription_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def delete_subscription(self, subscription_uri: str) -> RedfishResponse:
        return asyncio.run(self.delete_subscription_async(subscription_uri))

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------

    async def subscribe_sse(
        self,
        filters: dict | None = None,
    ) -> AsyncGenerator[RedfishEvent, None]:
        """
        Opens a Server-Sent Events stream from the BMC's EventService.
        Yields RedfishEvent objects as they arrive.
        """
        import httpx

        sse_uri = f"{self._service_uri}/SSE"
        if filters:
            params = "&".join(f"{k}={v}" for k, v in filters.items())
            sse_uri = f"{sse_uri}?{params}"

        headers = AuthManager.attach_auth(self._auth_state, {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        })

        async with httpx.AsyncClient(
            base_url=str(self._http._base_url),
            verify=self._http._verify,
            timeout=None,
        ) as client:
            async with client.stream("GET", sse_uri, headers=headers) as response:
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        event = _parse_sse_block(block)
                        if event:
                            yield event

    # ------------------------------------------------------------------
    # Test event
    # ------------------------------------------------------------------

    async def submit_test_event_async(self, event_data: dict) -> RedfishResponse:
        uri = f"{self._service_uri}/Actions/EventService.SubmitTestEvent"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", uri, headers=headers, body=event_data)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def submit_test_event(self, event_data: dict) -> RedfishResponse:
        return asyncio.run(self.submit_test_event_async(event_data))


# ------------------------------------------------------------------
# SSE helpers
# ------------------------------------------------------------------

def _parse_sse_block(block: str) -> RedfishEvent | None:
    data = ""
    for line in block.strip().splitlines():
        if line.startswith("data:"):
            data += line[5:].strip()
    if not data:
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None

    events_list = payload.get("Events", [payload])
    if not events_list:
        return None
    ev = events_list[0]
    return RedfishEvent(
        event_id=str(ev.get("EventId", "")),
        event_type=ev.get("EventType", ""),
        event_timestamp=ev.get("EventTimestamp", ""),
        message_id=ev.get("MessageId", ""),
        message=ev.get("Message", ""),
        severity=ev.get("Severity", ""),
        origin_of_condition=ev.get("OriginOfCondition", {}).get("@odata.id"),
        raw=ev,
    )
