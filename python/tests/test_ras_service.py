# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
tests/test_ras_service.py

Unit tests for the RAS API service layer:
  - CperSeverity inference from MessageId strings
  - CperEvent parsing from Redfish event records
  - RasServiceHandle.discover_endpoints()
  - RasServiceHandle.subscribe_cper_events()
  - RasServiceHandle.fetch_cper_data()
  - RasServiceHandle.submit_cpad()
  - RasServiceHandle.parse_cper_events()
"""

from __future__ import annotations

import base64

import pytest

from redfish_sdk import (
    CpadRecord,
    CperEvent,
    CperSeverity,
    RasEndpoint,
    RasServiceHandle,
)
from redfish_sdk.context import ClientContext
from redfish_sdk.models.redfish_types import (
    AuthState,
    ConnectionConfig,
    EndpointCapabilities,
    RawHttpResponse,
    TimeoutConfig,
)
from redfish_sdk.transport.http_client import MockHttpClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(routes: dict) -> ClientContext:
    mock = MockHttpClient(routes)
    return ClientContext(
        mock,
        AuthState(),
        EndpointCapabilities(),
        ConnectionConfig(),
        TimeoutConfig(),
    )


# ---------------------------------------------------------------------------
# CperSeverity
# ---------------------------------------------------------------------------

class TestCperSeverity:
    def test_corrected(self):
        assert CperSeverity.from_message_id("RASEvent.1.0.CorrectedError") == CperSeverity.CORRECTED

    def test_fatal(self):
        assert CperSeverity.from_message_id("RASEvent.1.0.FatalCrash") == CperSeverity.FATAL

    def test_informational(self):
        assert CperSeverity.from_message_id("RAS.Informational.PoisonGen") == CperSeverity.INFORMATIONAL

    def test_recoverable(self):
        assert CperSeverity.from_message_id("RAS.1.0.RecoverableError") == CperSeverity.RECOVERABLE

    def test_platform_event(self):
        assert CperSeverity.from_message_id("RAS.PlatformEvent.ActionAck") == CperSeverity.PLATFORM_EVENT

    def test_case_insensitive(self):
        assert CperSeverity.from_message_id("ras.event.FATAL") == CperSeverity.FATAL

    def test_unknown_registry(self):
        assert CperSeverity.from_message_id("Chassis.1.0.PowerCycled") is None

    def test_empty_string(self):
        assert CperSeverity.from_message_id("") is None


# ---------------------------------------------------------------------------
# CperEvent.from_event_record
# ---------------------------------------------------------------------------

class TestCperEventParsing:
    def test_inline_cper_via_additional_data(self):
        payload = b"\x00\x01\x02\x03\xFF"
        record = {
            "EventId":        "evt-001",
            "MessageId":      "RASEvent.1.0.CorrectedError",
            "EventTimestamp": "2026-05-18T10:00:00Z",
            "AdditionalData": base64.b64encode(payload).decode(),
        }
        ev = CperEvent.from_event_record(record)
        assert ev.event_id    == "evt-001"
        assert ev.severity    == CperSeverity.CORRECTED
        assert ev.cper_data   == payload
        assert ev.additional_data_uri is None

    def test_inline_cper_via_oem_field(self):
        payload = b"\xDE\xAD\xBE\xEF"
        record = {
            "EventId":        "evt-002",
            "MessageId":      "RASEvent.1.0.Fatal",
            "EventTimestamp": "2026-05-18T10:01:00Z",
            "Oem":            {"CperData": base64.b64encode(payload).decode()},
        }
        ev = CperEvent.from_event_record(record)
        assert ev.cper_data == payload
        assert ev.severity  == CperSeverity.FATAL

    def test_large_cper_additional_data_uri(self):
        record = {
            "EventId":          "evt-003",
            "MessageId":        "RASEvent.1.0.Recoverable",
            "EventTimestamp":   "2026-05-18T10:02:00Z",
            "AdditionalDataURI": "/redfish/v1/CPERData/abc123",
        }
        ev = CperEvent.from_event_record(record)
        assert ev.cper_data           is None
        assert ev.additional_data_uri == "/redfish/v1/CPERData/abc123"
        assert ev.severity            == CperSeverity.RECOVERABLE

    def test_origin_of_condition_parsed(self):
        record = {
            "EventId":           "evt-004",
            "MessageId":         "RASEvent.1.0.Corrected",
            "EventTimestamp":    "",
            "OriginOfCondition": {"@odata.id": "/redfish/v1/Systems/1/Memory/DIMM_A0"},
        }
        ev = CperEvent.from_event_record(record)
        assert ev.origin_of_condition == "/redfish/v1/Systems/1/Memory/DIMM_A0"

    def test_invalid_base64_does_not_raise(self):
        record = {
            "EventId":        "evt-005",
            "MessageId":      "RASEvent.1.0.Fatal",
            "EventTimestamp": "",
            "AdditionalData": "!!!not-valid-base64!!!",
        }
        ev = CperEvent.from_event_record(record)
        assert ev.cper_data is None   # graceful fallback

    def test_empty_record(self):
        ev = CperEvent.from_event_record({})
        assert ev.event_id  == ""
        assert ev.severity  is None
        assert ev.cper_data is None


# ---------------------------------------------------------------------------
# RasServiceHandle.parse_cper_events (static)
# ---------------------------------------------------------------------------

class TestParseCperEvents:
    def test_filters_to_ras_only(self):
        payload = {
            "Events": [
                {"EventId": "1", "MessageId": "RASEvent.1.0.Corrected",   "EventTimestamp": ""},
                {"EventId": "2", "MessageId": "Chassis.1.0.PowerCycled",  "EventTimestamp": ""},
                {"EventId": "3", "MessageId": "RASEvent.1.0.Fatal",       "EventTimestamp": ""},
                {"EventId": "4", "MessageId": "SomeRegistry.CPER.Event",  "EventTimestamp": ""},
            ]
        }
        events = RasServiceHandle.parse_cper_events(payload)
        ids = {e.event_id for e in events}
        # EventId 2 is not RAS; 1, 3, 4 are (4 contains "cper" in message id)
        assert ids == {"1", "3", "4"}
        assert "2" not in ids

    def test_empty_events_list(self):
        assert RasServiceHandle.parse_cper_events({"Events": []}) == []

    def test_missing_events_key(self):
        assert RasServiceHandle.parse_cper_events({}) == []

    def test_ras_in_message_id_included(self):
        payload = {"Events": [
            {"EventId": "x", "MessageId": "Custom.RAS.Something", "EventTimestamp": ""},
        ]}
        events = RasServiceHandle.parse_cper_events(payload)
        assert len(events) == 1


# ---------------------------------------------------------------------------
# RasServiceHandle.discover_endpoints
# ---------------------------------------------------------------------------

class TestDiscoverEndpoints:
    def test_empty_collection(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/RasService"): RawHttpResponse(
                200, {},
                "", {"Members": []}
            ),
        })
        eps = ctx.ras_service.discover_endpoints()
        assert eps == []

    def test_one_endpoint(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/RasService"): RawHttpResponse(
                200, {},
                "", {"Members": [{"@odata.id": "/redfish/v1/RasService/Endpoints/0"}]}
            ),
            ("GET", "/redfish/v1/RasService/Endpoints/0"): RawHttpResponse(
                200, {},
                "", {
                    "Id":              "ep0",
                    "CreatorId":       "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "FruId":           "11111111-2222-3333-4444-555555555555",
                    "PartitionId":     "P0",
                    "SupportedQueues": ["Event", "Corrected", "Recoverable", "Fatal", "Action"],
                }
            ),
        })
        eps = ctx.ras_service.discover_endpoints()
        assert len(eps) == 1
        ep = eps[0]
        assert ep.endpoint_id  == "ep0"
        assert ep.creator_id   == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert ep.partition_id == "P0"
        assert "Corrected" in ep.supported_queues
        assert "Action" in ep.supported_queues

    def test_two_endpoints(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/RasService"): RawHttpResponse(
                200, {},
                "", {"Members": [
                    {"@odata.id": "/redfish/v1/RasService/Endpoints/0"},
                    {"@odata.id": "/redfish/v1/RasService/Endpoints/1"},
                ]}
            ),
            ("GET", "/redfish/v1/RasService/Endpoints/0"): RawHttpResponse(
                200, {},
                "", {"Id": "ep0", "CreatorId": "a", "FruId": "b", "PartitionId": "P0"}
            ),
            ("GET", "/redfish/v1/RasService/Endpoints/1"): RawHttpResponse(
                200, {},
                "", {"Id": "ep1", "CreatorId": "c", "FruId": "d", "PartitionId": "P1"}
            ),
        })
        eps = ctx.ras_service.discover_endpoints()
        assert len(eps) == 2
        assert {ep.partition_id for ep in eps} == {"P0", "P1"}

    def test_discovery_failure_returns_empty(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/RasService"): RawHttpResponse(
                503, {},
                "Service Unavailable", None
            ),
        })
        eps = ctx.ras_service.discover_endpoints()
        assert eps == []

    def test_endpoint_detail_failure_skipped(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/RasService"): RawHttpResponse(
                200, {},
                "", {"Members": [
                    {"@odata.id": "/redfish/v1/RasService/Endpoints/0"},
                    {"@odata.id": "/redfish/v1/RasService/Endpoints/1"},
                ]}
            ),
            ("GET", "/redfish/v1/RasService/Endpoints/0"): RawHttpResponse(
                200, {},
                "", {"Id": "ep0", "CreatorId": "", "FruId": "", "PartitionId": "P0"}
            ),
            ("GET", "/redfish/v1/RasService/Endpoints/1"): RawHttpResponse(
                404, {},
                "Not Found", None
            ),
        })
        eps = ctx.ras_service.discover_endpoints()
        assert len(eps) == 1
        assert eps[0].endpoint_id == "ep0"


# ---------------------------------------------------------------------------
# RasServiceHandle.subscribe_cper_events
# ---------------------------------------------------------------------------

class TestSubscribeCperEvents:
    def test_subscribe_with_registry_prefix(self):
        ctx = _make_ctx({
            ("POST", "/redfish/v1/EventService/Subscriptions"): RawHttpResponse(
                201, {},
                "", {"@odata.id": "/redfish/v1/EventService/Subscriptions/ras1"}
            ),
        })
        resp = ctx.ras.subscribe_cper_events(
            "http://collector:9090/cper",
            registry_prefixes=["RASEvent"],
            context="RAS-Test",
        )
        assert resp.status_code == 201
        assert resp.success

    def test_subscribe_with_message_ids(self):
        ctx = _make_ctx({
            ("POST", "/redfish/v1/EventService/Subscriptions"): RawHttpResponse(
                201, {},
                "", {}
            ),
        })
        resp = ctx.ras.subscribe_cper_events(
            "http://collector:9090/cper",
            message_ids=["RASEvent.1.0.CorrectedError", "RASEvent.1.0.FatalError"],
        )
        assert resp.status_code == 201

    def test_subscribe_no_filters(self):
        """Subscribing without filters is valid — caller receives all events."""
        ctx = _make_ctx({
            ("POST", "/redfish/v1/EventService/Subscriptions"): RawHttpResponse(
                201, {},
                "", {}
            ),
        })
        resp = ctx.ras.subscribe_cper_events("http://collector:9090/cper")
        assert resp.status_code == 201

    def test_subscribe_failure_propagated(self):
        ctx = _make_ctx({
            ("POST", "/redfish/v1/EventService/Subscriptions"): RawHttpResponse(
                400, {},
                "", {"error": {"message": "Bad destination"}}
            ),
        })
        resp = ctx.ras.subscribe_cper_events("not-a-valid-url")
        assert resp.status_code == 400
        assert not resp.success


# ---------------------------------------------------------------------------
# RasServiceHandle.fetch_cper_data
# ---------------------------------------------------------------------------

class TestFetchCperData:
    def test_fetch_cper_data_field(self):
        payload = b"\xCA\xFE\xBA\xBE"
        ctx = _make_ctx({
            ("GET", "/redfish/v1/CPERData/x1"): RawHttpResponse(
                200, {},
                "", {"CperData": base64.b64encode(payload).decode()}
            ),
        })
        data = ctx.ras.fetch_cper_data("/redfish/v1/CPERData/x1")
        assert data == payload

    def test_fetch_data_field(self):
        payload = b"\x01\x02\x03"
        ctx = _make_ctx({
            ("GET", "/redfish/v1/CPERData/x2"): RawHttpResponse(
                200, {},
                "", {"Data": base64.b64encode(payload).decode()}
            ),
        })
        data = ctx.ras.fetch_cper_data("/redfish/v1/CPERData/x2")
        assert data == payload

    def test_fetch_additional_data_field(self):
        payload = b"\xFF\xFE"
        ctx = _make_ctx({
            ("GET", "/redfish/v1/CPERData/x3"): RawHttpResponse(
                200, {},
                "", {"AdditionalData": base64.b64encode(payload).decode()}
            ),
        })
        data = ctx.ras.fetch_cper_data("/redfish/v1/CPERData/x3")
        assert data == payload

    def test_fetch_failure_raises(self):
        ctx = _make_ctx({
            ("GET", "/redfish/v1/CPERData/missing"): RawHttpResponse(
                404, {},
                "Not Found", None
            ),
        })
        with pytest.raises(RuntimeError, match="404"):
            ctx.ras.fetch_cper_data("/redfish/v1/CPERData/missing")


# ---------------------------------------------------------------------------
# RasServiceHandle.submit_cpad
# ---------------------------------------------------------------------------

class TestSubmitCpad:
    def test_submit_accepted(self):
        ctx = _make_ctx({
            ("PUT", "/redfish/v1/RAS/CPADs"): RawHttpResponse(
                202, {},
                "", {}
            ),
        })
        cpad = CpadRecord(
            platform_id  = "bmc-01",
            partition_id = "P0",
            creator_id   = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            payload      = b"\xDE\xAD\xBE\xEF",
        )
        resp = ctx.ras.submit_cpad("/redfish/v1/RAS/CPADs", cpad)
        assert resp.status_code == 202
        assert resp.success

    def test_submit_with_fru_fields(self):
        ctx = _make_ctx({
            ("PUT", "/redfish/v1/RAS/CPADs"): RawHttpResponse(
                202, {},
                "", {}
            ),
        })
        cpad = CpadRecord(
            platform_id  = "bmc-01",
            partition_id = "P1",
            creator_id   = "creator-guid",
            payload      = b"\x00",
            fru_id       = "fru-guid",
            fru_text     = "DIMM_A0 (PCIe slot 2, left riser)",
        )
        resp = ctx.ras.submit_cpad("/redfish/v1/RAS/CPADs", cpad)
        assert resp.status_code == 202

    def test_submit_rejected_propagated(self):
        ctx = _make_ctx({
            ("PUT", "/redfish/v1/RAS/CPADs"): RawHttpResponse(
                422, {},
                "", {"error": {"message": "Unknown PartitionId"}}
            ),
        })
        cpad = CpadRecord("bmc", "bad-partition", "creator", b"\x00")
        resp = ctx.ras.submit_cpad("/redfish/v1/RAS/CPADs", cpad)
        assert resp.status_code == 422
        assert not resp.success


# ---------------------------------------------------------------------------
# ctx.ras alias
# ---------------------------------------------------------------------------

class TestContextAliases:
    def test_ras_alias_same_object(self):
        ctx = _make_ctx({})
        assert ctx.ras is ctx.ras_service

    def test_ras_service_is_ras_service_handle(self):
        ctx = _make_ctx({})
        assert isinstance(ctx.ras_service, RasServiceHandle)
