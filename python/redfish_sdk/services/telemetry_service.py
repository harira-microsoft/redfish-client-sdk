# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/services/telemetry_service.py

TelemetryService handle — metric definitions, reports, SSE streaming.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

_DEFAULT_SERVICE_PATH = "/redfish/v1/TelemetryService"


@dataclass
class MetricValue:
    metric_id: str = ""
    metric_value: str | float | int = ""
    timestamp: str = ""
    metric_property: str | None = None


@dataclass
class MetricReport:
    report_id: str = ""
    report_uri: str = ""
    timestamp: str = ""
    metric_values: list[MetricValue] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class TelemetryServiceHandle:

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
        return self._discovery_map.get("TelemetryService", _DEFAULT_SERVICE_PATH)

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
    # Metric Report Definitions
    # ------------------------------------------------------------------

    async def list_metric_report_definitions_async(self) -> RedfishResponse:
        uri = f"{self._service_uri}/MetricReportDefinitions"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_metric_report_definitions(self) -> RedfishResponse:
        return asyncio.run(self.list_metric_report_definitions_async())

    async def get_metric_report_definition_async(self, definition_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", definition_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_metric_report_definition(self, definition_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_metric_report_definition_async(definition_uri))

    # ------------------------------------------------------------------
    # Metric Reports
    # ------------------------------------------------------------------

    async def list_metric_reports_async(self) -> RedfishResponse:
        uri = f"{self._service_uri}/MetricReports"
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def list_metric_reports(self) -> RedfishResponse:
        return asyncio.run(self.list_metric_reports_async())

    async def get_metric_report_async(self, report_uri: str) -> RedfishResponse:
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", report_uri, headers=headers)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def get_metric_report(self, report_uri: str) -> RedfishResponse:
        return asyncio.run(self.get_metric_report_async(report_uri))

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------

    async def stream_metric_reports(
        self,
        definition_uri: str | None = None,
    ) -> AsyncGenerator[MetricReport, None]:
        """
        Streams metric reports via SSE from the TelemetryService.
        Yields MetricReport objects as they arrive.
        """
        import httpx

        sse_uri = f"{self._service_uri}/SSE"
        if definition_uri:
            sse_uri = f"{sse_uri}?$filter=MetricReportDefinition eq '{definition_uri}'"

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
                        report = _parse_metric_sse_block(block)
                        if report:
                            yield report


def _parse_metric_sse_block(block: str) -> MetricReport | None:
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

    values = [
        MetricValue(
            metric_id=v.get("MetricId", ""),
            metric_value=v.get("MetricValue", ""),
            timestamp=v.get("Timestamp", ""),
            metric_property=v.get("MetricProperty"),
        )
        for v in payload.get("MetricValues", [])
    ]
    return MetricReport(
        report_id=payload.get("Id", ""),
        report_uri=payload.get("@odata.id", ""),
        timestamp=payload.get("Timestamp", ""),
        metric_values=values,
        raw=payload,
    )
