# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/services/log_service.py

LogService handle — list services, get/filter entries, clear log.
Imports: protocol, transport.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SEL parsing — FR6.6 (ported from team Rust client, src/events.rs)
# ---------------------------------------------------------------------------
# IPMI SEL record type bytes for OpenBMC OEM timestamped events
_SEL_TYPE_PXE = 0xCA       # PXE boot events
_SEL_TYPE_HOST_OS = 0xD9   # Host OS state events
# Host OS event subtypes (byte 13 of the 16-byte SEL record)
_HOST_OS_MODE_CHANGE = 0x01
_HOST_OS_HAND_OFF = 0x02


@dataclass
class ParsedSelRecord:
    """
    Decoded IPMI SEL binary record.

    record_type values:
      - ``"PxeBoot"``       — OEM PXE boot event (record type byte 0xCA)
      - ``"HostOsModeChange"`` — Host OS trust mode change (0xD9, subtype 0x01)
      - ``"HostOsHandOff"`` — Host OS hand-off (0xD9, subtype 0x02)
      - ``"Unknown"``       — any other record type byte
    """
    record_type: str
    record_id: int
    timestamp_raw: int          # Unix epoch from SEL bytes (not the Redfish 'created' field)
    raw_hex: str                # normalised uppercase hex, no spaces
    raw_bytes: list[int]
    sensor_type: int | None = None
    sensor_number: int | None = None
    event_dir_type: int | None = None
    event_data: list[int] = field(default_factory=list)
    description: str = ""


def parse_sel_entry(raw_hex: str) -> ParsedSelRecord:
    """
    Parse a raw IPMI SEL record from a hex string.

    Accepts the raw hex directly or with an OpenBMC ``"Raw Data : Hex "``
    prefix (as found in ``LogEntry.MessageArgs[0]``).

    Raises :class:`redfish_sdk.errors.RedfishSDKError` on invalid input.

    Real-world examples::

        # PXE boot start (OpenBMC)
        parse_sel_entry("b70fcad117db6837010000002000FFFF")
        # Host OS mode change (OpenBMC LogEntry.MessageArgs[0])
        parse_sel_entry("Raw Data : Hex e911d9df4cdc682000000401 01 01 0200")
        # Flat generator format — from SELRawText.txt replay (FR6.6 v0.3)
        parse_sel_entry("Raw data: 91 06 02 e9 6b e7 66 20 00 04 23 fe 6f 1d 0f 00")
    """
    from redfish_sdk.errors import RedfishSDKError

    cleaned = raw_hex.strip()
    # Strip OpenBMC prefix: "Raw Data : Hex <hex>"
    if "Raw Data : Hex " in cleaned:
        cleaned = cleaned.split("Raw Data : Hex ")[-1].strip()
    # Strip flat generator prefix: "Raw data: <hex>"  (FR6.6 v0.3)
    elif cleaned.lower().startswith("raw data:"):
        cleaned = cleaned[len("raw data:"):].strip()
    cleaned = cleaned.replace(" ", "").upper()

    if len(cleaned) < 32:
        raise RedfishSDKError(
            f"SEL record too short: {len(cleaned)} hex chars (need >= 32 for 16 bytes)"
        )

    try:
        raw = bytes.fromhex(cleaned[:32])  # always take the first 16 bytes
    except ValueError as exc:
        raise RedfishSDKError(f"Invalid hex in SEL record: {exc}") from exc

    record_id = int.from_bytes(raw[0:2], "little")
    record_type_byte = raw[2]
    timestamp_raw = int.from_bytes(raw[3:7], "little")

    logger.debug(
        "parse_sel_entry: record_id=0x%04X type=0x%02X timestamp=%d",
        record_id, record_type_byte, timestamp_raw,
    )

    if record_type_byte == _SEL_TYPE_PXE:
        return ParsedSelRecord(
            record_type="PxeBoot",
            record_id=record_id,
            timestamp_raw=timestamp_raw,
            raw_hex=cleaned,
            raw_bytes=list(raw),
            event_data=list(raw[12:15]),
            description="PXE boot event",
        )

    if record_type_byte == _SEL_TYPE_HOST_OS:
        subtype = raw[13]
        if subtype == _HOST_OS_MODE_CHANGE:
            rtype, desc = "HostOsModeChange", "Host OS trust mode change"
        elif subtype == _HOST_OS_HAND_OFF:
            rtype, desc = "HostOsHandOff", "Host OS hand-off"
        else:
            rtype, desc = "HostOsUnknown", f"Host OS event subtype 0x{subtype:02X}"
        return ParsedSelRecord(
            record_type=rtype,
            record_id=record_id,
            timestamp_raw=timestamp_raw,
            raw_hex=cleaned,
            raw_bytes=list(raw),
            sensor_type=raw[10],
            sensor_number=raw[11],
            event_dir_type=raw[12],
            event_data=list(raw[12:15]),
            description=desc,
        )

    # Standard system event (0x02) or unrecognised OEM type
    return ParsedSelRecord(
        record_type="Unknown",
        record_id=record_id,
        timestamp_raw=timestamp_raw,
        raw_hex=cleaned,
        raw_bytes=list(raw),
        sensor_type=raw[10] if len(raw) > 10 else None,
        sensor_number=raw[11] if len(raw) > 11 else None,
        event_dir_type=raw[12] if len(raw) > 12 else None,
        event_data=list(raw[13:16]) if len(raw) > 13 else [],
        description=f"Unrecognised SEL record type 0x{record_type_byte:02X}",
    )

_DEFAULT_SERVICE_PATH = "/redfish/v1/Systems/1/LogServices"


@dataclass
class LogFilter:
    """OData query parameters for log entry retrieval.

    Parameters are applied in the BMC-required order:
    ``$skip`` → ``$top`` → ``$filter``.

    ``odata_filter`` is an escape-hatch for any raw OData expression.
    It overrides ``severity`` and ``message_id`` if set.
    """
    top:          int | None = None   # $top  — max entries to return
    skip:         int | None = None   # $skip — first N entries to skip (FR6.8)
    severity:     str | None = None   # $filter=Severity eq '<value>'
    message_id:   str | None = None   # $filter=MessageId eq '<value>'
    odata_filter: str | None = None   # raw $filter (overrides severity / message_id)


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
        """Discover all LogService instances across Systems and Managers.

        Redfish LogServices are not at a top-level URI — they live under
        each System and Manager member.  This method walks both collections
        and returns a synthetic aggregated collection response so callers
        can iterate Members[] without knowing the tree layout.
        """
        logger.debug("list_services: walking /redfish/v1/Systems and /redfish/v1/Managers")
        headers = AuthManager.attach_auth(self._auth_state, {})
        all_members: list[dict] = []

        for collection_path in ("/redfish/v1/Systems", "/redfish/v1/Managers"):
            raw = await self._http.request_async("GET", collection_path, headers=headers)
            if raw.status_code != 200 or not isinstance(raw.body_json, dict):
                continue
            for member in raw.body_json.get("Members", []):
                member_uri = member.get("@odata.id", "")
                if not member_uri:
                    continue
                log_raw = await self._http.request_async(
                    "GET", f"{member_uri}/LogServices", headers=headers
                )
                if log_raw.status_code == 200 and isinstance(log_raw.body_json, dict):
                    all_members.extend(log_raw.body_json.get("Members", []))

        if not all_members:
            # Fallback: try the URI from discovery map or default path
            raw = await self._http.request_async("GET", self._service_uri, headers=headers)
            return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

        synthetic_body: dict = {
            "@odata.type": "#LogServiceCollection.LogServiceCollection",
            "Name": "Log Services",
            "Members": all_members,
            "Members@odata.count": len(all_members),
        }
        return build_response(200, {}, synthetic_body, "")

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

    # ------------------------------------------------------------------
    # Pagination iterator (FR6.5 / FR6.8)
    # ------------------------------------------------------------------

    async def iter_entries_async(
        self,
        log_service_uri: str,
        filter: LogFilter | None = None,
        max_pages: int | None = None,
    ) -> AsyncIterator[RedfishResponse]:
        """Async generator that follows ``Members@odata.nextLink`` across pages.

        Yields one :class:`RedfishResponse` per page.  Stops when
        ``nextLink`` is absent or *max_pages* is reached.
        """
        page = 0
        # Build URI for first page (honour $skip / $top / $filter from filter)
        entries_uri: str | None = f"{log_service_uri.rstrip('/')}/Entries"
        query_params = _build_filter_params(filter)
        if query_params:
            entries_uri = f"{entries_uri}?{query_params}"

        headers = AuthManager.attach_auth(self._auth_state, {})

        while entries_uri is not None:
            if max_pages is not None and page >= max_pages:
                break
            raw = await self._http.request_async("GET", entries_uri, headers=headers)
            resp = build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)
            yield resp
            page += 1
            if not resp.success or not isinstance(resp.body, dict):
                break
            # Follow nextLink if present
            next_link = resp.body.get("Members@odata.nextLink")
            entries_uri = next_link if next_link else None

    def iter_entries(
        self,
        log_service_uri: str,
        filter: LogFilter | None = None,
        max_pages: int | None = None,
    ) -> Iterator[RedfishResponse]:
        """Sync wrapper around :meth:`iter_entries_async`."""
        import queue as _queue
        import threading as _threading

        q: _queue.Queue[RedfishResponse | BaseException | None] = _queue.Queue()

        async def _producer() -> None:
            try:
                async for page in self.iter_entries_async(
                    log_service_uri, filter, max_pages
                ):
                    q.put(page)
            except BaseException as exc:  # noqa: BLE001
                q.put(exc)
            finally:
                q.put(None)  # sentinel

        def _run() -> None:
            asyncio.run(_producer())

        t = _threading.Thread(target=_run, daemon=True)
        t.start()
        while True:
            item = q.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
        t.join()


def _build_filter_params(filter: LogFilter | None) -> str:
    """Build an OData query string from a *LogFilter*.

    Order is always ``$skip`` → ``$top`` → ``$filter`` per FR6.7 /
    OpenBMC implementation requirements.
    """
    if not filter:
        return ""
    parts: list[str] = []
    # $skip first
    if filter.skip is not None:
        parts.append(f"$skip={filter.skip}")
    # $top second
    if filter.top is not None:
        parts.append(f"$top={filter.top}")
    # $filter last
    if filter.odata_filter:
        parts.append(f"$filter={filter.odata_filter}")
    elif filter.severity:
        parts.append(f"$filter=Severity eq '{filter.severity}'")
    elif filter.message_id:
        parts.append(f"$filter=MessageId eq '{filter.message_id}'")
    return "&".join(parts)
