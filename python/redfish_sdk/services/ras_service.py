# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/services/ras_service.py

RasService handle — RAS API endpoint discovery, CPER event subscription,
large-CPER retrieval via AdditionalDataUri, and CPAD submission.

Terminology (OCP Fault Management Infrastructure / UEFI RAS API spec):
  CPER  — Common Platform Error Record (UEFI 2.9A)
  CPAD  — Common Platform Action Descriptor (OCP RAS API v1.0)
  CreatorID   — GUID identifying the vendor analyzer for a set of CPERs.
  PartitionID — BMC-assigned ID that uniquely identifies a silicon endpoint;
                used to route CPADs back to the right component.
  FRU ID/Text — Field-Replaceable Unit identifier / human-readable location.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from redfish_sdk.protocol.response import RedfishResponse, build_response
from redfish_sdk.transport.auth import AuthManager

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState

logger = logging.getLogger(__name__)

# Default RAS service root path.  Update to the standardised OCP URI once
# the RAS API Redfish registry is finalised.
_DEFAULT_SERVICE_PATH = "/redfish/v1/RasService"

# Registry prefixes used when subscribing to CPER events.  Populate this list
# with the finalised OCP RAS registry prefix (e.g. "RASEvent") before use.
RAS_REGISTRY_PREFIXES: list[str] = []


# ---------------------------------------------------------------------------
# CPER severity / queue types
# ---------------------------------------------------------------------------

class CperSeverity(Enum):
    """
    Maps to the five RAS API CPER queues defined in the OCP RAS API v1.0 spec.

    Queue         Description
    ─────────────────────────────────────────────────────────────────────────
    PlatformEvent Informational CPERs / Platform Action Events (not errors)
    Informational Deferred errors including poison generation
    Corrected     Hardware-corrected errors
    Recoverable   Errors where the OS may survive (poison consumption, PCIe)
    Fatal         Errors that crash the OS / generate hardware crashdumps
    """
    PLATFORM_EVENT = "PlatformEvent"
    INFORMATIONAL  = "Informational"
    CORRECTED      = "Corrected"
    RECOVERABLE    = "Recoverable"
    FATAL          = "Fatal"

    @classmethod
    def from_message_id(cls, message_id: str) -> "CperSeverity | None":
        """Infer severity from a Redfish MessageId string (case-insensitive)."""
        lower = message_id.lower()
        for sev in cls:
            if sev.value.lower() in lower:
                return sev
        return None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RasEndpoint:
    """
    A silicon RAS API endpoint discovered by the BMC and exposed via Redfish.

    The BMC performs MCTP/PLDM enumeration and populates these fields from
    the RAS API discovery exchange with each endpoint.
    """
    endpoint_id:      str
    creator_id:       str               # GUID — identifies the vendor analyzer
    fru_id:           str               # GUID — unique FRU instance identifier
    partition_id:     str               # BMC-assigned routing ID for CPADs
    supported_queues: list[str] = field(default_factory=list)
    uri:              str = ""          # Redfish URI for this endpoint resource
    raw:              dict = field(default_factory=dict)


@dataclass
class CperEvent:
    """
    A CPER-carrying Redfish event delivered by the BMC.

    For small CPERs the ``cper_data`` field is populated directly with the
    decoded binary payload.  For large CPERs the BMC sets ``additional_data_uri``
    instead; call ``RasServiceHandle.fetch_cper_data()`` to retrieve the blob.
    """
    event_id:            str
    message_id:          str
    severity:            CperSeverity | None
    timestamp:           str
    origin_of_condition: str | None = None
    cper_data:           bytes | None = None    # inline CPER bytes (base64-decoded)
    additional_data_uri: str | None = None      # URI for large-CPER retrieval
    raw:                 dict = field(default_factory=dict)

    @classmethod
    def from_event_record(cls, record: dict) -> "CperEvent":
        """Parse a single EventRecord dict from a Redfish EventMessage payload."""
        message_id = record.get("MessageId", "")
        severity   = CperSeverity.from_message_id(message_id)

        # Inline CPER: may be base64-encoded in AdditionalData or a vendor
        # extension field such as Oem.CperData.
        cper_data: bytes | None = None
        raw_cper = (
            record.get("AdditionalData")
            or record.get("Oem", {}).get("CperData")
        )
        if isinstance(raw_cper, str):
            try:
                cper_data = base64.b64decode(raw_cper)
            except Exception:
                pass

        return cls(
            event_id            = record.get("EventId", ""),
            message_id          = message_id,
            severity            = severity,
            timestamp           = record.get("EventTimestamp", ""),
            origin_of_condition = record.get("OriginOfCondition", {}).get("@odata.id"),
            cper_data           = cper_data,
            additional_data_uri = record.get("AdditionalDataURI"),
            raw                 = record,
        )


@dataclass
class CpadRecord:
    """
    A Common Platform Action Descriptor (CPAD) to submit to the BMC.

    The BMC uses ``partition_id`` to route the action to the correct silicon
    endpoint.  ``platform_id`` must match the value the BMC advertises in its
    own CPERs so the fleet infrastructure can direct the CPAD here.

    ``payload`` is the raw binary CPAD blob as defined in the OCP RAS API spec.
    It is transmitted base64-encoded in the JSON body.
    """
    platform_id:  str               # identifies this BMC within the fleet
    partition_id: str               # identifies the target silicon endpoint
    creator_id:   str               # identifies the issuing analyzer
    payload:      bytes             # binary CPAD blob
    fru_id:       str = ""
    fru_text:     str = ""          # physical location label (e.g. silkscreen)


# ---------------------------------------------------------------------------
# Service handle
# ---------------------------------------------------------------------------

class RasServiceHandle:
    """
    Redfish client handle for the RAS API service.

    Provides:
      - Discovery of BMC-exposed RAS API endpoints (silicon components).
      - CPER event subscription (wraps EventService with RAS message IDs).
      - Large-CPER retrieval via AdditionalDataUri.
      - CPAD submission (PUT to the BMC's CPAD URI).
      - Static helper to parse CperEvent objects from a push-mode payload.
    """

    def __init__(
        self,
        http: "HttpClient",
        auth_state: "AuthState",
        discovery_map: dict[str, str],
    ) -> None:
        self._http = http
        self._auth_state = auth_state
        self._discovery_map = discovery_map

    @property
    def _service_uri(self) -> str:
        return self._discovery_map.get("RasService", _DEFAULT_SERVICE_PATH)

    # ------------------------------------------------------------------
    # Endpoint discovery
    # ------------------------------------------------------------------

    async def discover_endpoints_async(self) -> list[RasEndpoint]:
        """
        Query the BMC for all discovered RAS API endpoints.

        The BMC populates this collection during MCTP/PLDM enumeration.
        Each member includes Creator ID, FRU ID, Partition ID, and the
        supported CPER queues confirmed during RAS API discovery.
        """
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", self._service_uri, headers=headers)
        resp = build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)
        if not resp.success:
            logger.warning("RAS endpoint discovery failed: HTTP %s", resp.status_code)
            return []

        endpoints: list[RasEndpoint] = []
        for member in resp.body.get("Members", []):
            uri = member.get("@odata.id", "")
            if not uri:
                continue
            dr = await self._http.request_async("GET", uri, headers=headers)
            detail = build_response(dr.status_code, dr.headers, dr.body_json, dr.body_text)
            if detail.success:
                d = detail.body
                endpoints.append(RasEndpoint(
                    endpoint_id      = d.get("Id", ""),
                    creator_id       = d.get("CreatorId", ""),
                    fru_id           = d.get("FruId", ""),
                    partition_id     = d.get("PartitionId", ""),
                    supported_queues = d.get("SupportedQueues", []),
                    uri              = uri,
                    raw              = d,
                ))

        logger.debug("RAS: discovered %d endpoint(s)", len(endpoints))
        return endpoints

    def discover_endpoints(self) -> list[RasEndpoint]:
        return asyncio.run(self.discover_endpoints_async())

    # ------------------------------------------------------------------
    # CPER event subscription
    # ------------------------------------------------------------------

    async def subscribe_cper_events_async(
        self,
        destination:       str,
        registry_prefixes: list[str] | None = None,
        message_ids:       list[str] | None = None,
        context:           str = "RAS-CPER",
        event_format_type: str = "Event",
    ) -> RedfishResponse:
        """
        Subscribe to CPER-carrying Redfish events from this BMC.

        ``registry_prefixes`` and ``message_ids`` narrow the subscription to
        RAS-specific events.  If both are omitted, ``RAS_REGISTRY_PREFIXES`` is
        used (update that list once the OCP registry name is finalised; sending
        an empty subscription receives all events from the BMC).
        """
        effective_prefixes = (
            registry_prefixes if registry_prefixes is not None
            else list(RAS_REGISTRY_PREFIXES)
        )

        body: dict = {
            "Destination":     destination,
            "Protocol":        "Redfish",
            "SubscriptionType": "RedfishEvent",
            "Context":         context,
            "EventFormatType": event_format_type,
        }
        if effective_prefixes:
            body["RegistryPrefixes"] = effective_prefixes
        if message_ids:
            body["MessageIds"] = message_ids

        subs_uri = self._discovery_map.get("EventService", "/redfish/v1/EventService")
        subs_uri = f"{subs_uri}/Subscriptions"

        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("POST", subs_uri, headers=headers, body=body)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def subscribe_cper_events(self, destination: str, **kwargs) -> RedfishResponse:
        return asyncio.run(self.subscribe_cper_events_async(destination, **kwargs))

    # ------------------------------------------------------------------
    # Large-CPER retrieval
    # ------------------------------------------------------------------

    async def fetch_cper_data_async(self, additional_data_uri: str) -> bytes:
        """
        Retrieve a CPER payload from the BMC via the ``AdditionalDataUri``
        carried in a Redfish event.  Returns the raw bytes of the CPER blob.

        The BMC may encode the binary payload as base64 inside a JSON field
        (``CperData``, ``Data``, or ``AdditionalData``) or serve it as raw
        ``application/octet-stream``.  Both cases are handled.
        """
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("GET", additional_data_uri, headers=headers)
        if raw.status_code < 200 or raw.status_code >= 300:
            raise RuntimeError(
                f"Failed to fetch CPER data from {additional_data_uri!r}: "
                f"HTTP {raw.status_code}"
            )

        # JSON response — try known base64 fields in priority order
        if raw.body_json and isinstance(raw.body_json, dict):
            for key in ("CperData", "Data", "AdditionalData"):
                if key in raw.body_json:
                    try:
                        return base64.b64decode(raw.body_json[key])
                    except Exception:
                        pass
            # Fallback: return raw JSON serialised as bytes
            return json.dumps(raw.body_json).encode()

        # Raw binary / text fallback
        return (raw.body_text or "").encode()

    def fetch_cper_data(self, additional_data_uri: str) -> bytes:
        return asyncio.run(self.fetch_cper_data_async(additional_data_uri))

    # ------------------------------------------------------------------
    # CPAD submission
    # ------------------------------------------------------------------

    async def submit_cpad_async(self, cpad_uri: str, cpad: CpadRecord) -> RedfishResponse:
        """
        Submit a CPAD to the BMC via HTTP PUT.

        The BMC acknowledges receipt in the response (does not imply the action
        has been taken).  Action completion is signalled asynchronously via a
        Platform Action Event CPER on the Event queue.

        ``cpad_uri`` is the BMC's CPAD endpoint URI.  Discovery of this URI is
        not yet standardised; obtain it from the service root or BMC documentation.
        """
        body = {
            "PlatformId":  cpad.platform_id,
            "PartitionId": cpad.partition_id,
            "CreatorId":   cpad.creator_id,
            "FruId":       cpad.fru_id,
            "FruText":     cpad.fru_text,
            "Payload":     base64.b64encode(cpad.payload).decode(),
        }
        headers = AuthManager.attach_auth(self._auth_state, {})
        raw = await self._http.request_async("PUT", cpad_uri, headers=headers, body=body)
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def submit_cpad(self, cpad_uri: str, cpad: CpadRecord) -> RedfishResponse:
        return asyncio.run(self.submit_cpad_async(cpad_uri, cpad))

    # ------------------------------------------------------------------
    # Parse CPER events from a push-mode Redfish event payload
    # ------------------------------------------------------------------

    @staticmethod
    def parse_cper_events(event_payload: dict) -> list[CperEvent]:
        """
        Extract ``CperEvent`` objects from a Redfish EventMessage payload dict
        (the JSON body POSTed to your event listener by the BMC).

        Filters to records that are identifiable as RAS/CPER events — those
        where a severity can be inferred or the MessageId contains "cper"/"ras".
        Non-RAS events in the same payload are silently ignored.
        """
        events: list[CperEvent] = []
        for record in event_payload.get("Events", []):
            ev = CperEvent.from_event_record(record)
            mid_lower = ev.message_id.lower()
            if ev.severity is not None or "cper" in mid_lower or "ras" in mid_lower:
                events.append(ev)
        return events
