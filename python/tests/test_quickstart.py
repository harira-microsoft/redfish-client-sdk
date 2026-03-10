# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
tests/test_quickstart.py  ─  SDK Tutorial for New Developers
═══════════════════════════════════════════════════════════════════

READ THIS FILE before writing SDK client code.

Every class covers one concept. Comments explain *why*, not just *what*.
All tests use MockHttpClient — no simulator, no network, no hardware needed.

Run with:
    cd python/
    pytest tests/test_quickstart.py -v -s

Quick reference card:
    ctx = redfish_sdk.connect(host, port, credentials, auth_mode, config)
    ─ Direct requests:   ctx.get(uri)  ctx.post(uri, body)  ctx.patch(uri, body)  ctx.delete(uri)
    ─ Discovery:         ctx.discover()  →  DiscoveryResult
    ─ Events:            ctx.event_service.subscribe(destination, ...)
    ─ Logs:              ctx.log_service.get_entries(log_service_uri)
    ─ Telemetry:         ctx.telemetry_service.get_metric_reports()
    ─ Update:            ctx.update_service.push_firmware(path)
    ─ Tasks:             response.task.wait()  # when response.status_code == 202
"""

from __future__ import annotations

import asyncio
import json

import pytest

import redfish_sdk
from redfish_sdk import (
    AuthMode,
    ConnectionConfig,
    Credentials,
    MockHttpClient,
    RawHttpResponse,
    RedfishHTTPError,
    RedfishProtocolError,
    RedfishSDKError,
)
from redfish_sdk.context import ClientContext
from redfish_sdk.models.redfish_types import (
    AuthState,
    EndpointCapabilities,
    TimeoutConfig,
)
from redfish_sdk.services.event_service import EventServiceHandle
from redfish_sdk.services.log_service import LogFilter, LogServiceHandle

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _ok(body: dict) -> RawHttpResponse:
    """Simulate a 200 OK JSON response from the BMC."""
    return RawHttpResponse(
        200, {"content-type": "application/json"}, json.dumps(body), body
    )


def _created(
    body: dict,
    location: str = "/redfish/v1/EventService/Subscriptions/1",
) -> RawHttpResponse:
    """Simulate a 201 Created (e.g. new subscription)."""
    return RawHttpResponse(
        201,
        {"location": location, "content-type": "application/json"},
        json.dumps(body),
        body,
    )


def _accepted(
    location: str = "/redfish/v1/TaskService/Tasks/1",
) -> RawHttpResponse:
    """Simulate a 202 Accepted — BMC started a background task."""
    return RawHttpResponse(202, {"location": location}, "", {})


def _no_content() -> RawHttpResponse:
    """Simulate a 204 No Content (e.g. successful DELETE)."""
    return RawHttpResponse(204, {}, "", {})


def _not_found() -> RawHttpResponse:
    """Simulate a 404 Not Found."""
    body = {"error": {"message": "Not Found"}}
    return RawHttpResponse(404, {}, json.dumps(body), body)


def _auth_state(mode: AuthMode = AuthMode.STATELESS) -> AuthState:
    return AuthState(mode=mode, credentials=Credentials("admin", "password"))


def _make_ctx(
    routes: dict | None = None,
) -> tuple[ClientContext, MockHttpClient]:
    """
    Build a ClientContext backed by MockHttpClient.

    Pass a routes dict to pre-register responses:
        routes = {("GET", "/redfish/v1"): _ok({...})}

    Any route not registered returns 404 automatically.

    In real code you would call:
        ctx = redfish_sdk.connect(host, port, credentials, auth_mode, config)
    This helper lets you do the same thing without a network connection.
    """
    mock = MockHttpClient(routes or {})
    ctx = ClientContext(
        http=mock,
        auth_state=_auth_state(),
        capabilities=EndpointCapabilities(),
        config=ConnectionConfig(use_tls=False),
        timeouts=TimeoutConfig(),
    )
    return ctx, mock


# ─────────────────────────────────────────────────────────────────────────────
# Concept 1: MockHttpClient
# ─────────────────────────────────────────────────────────────────────────────


class TestMockTransport:
    """
    CONCEPT: MockHttpClient

    In production your code calls redfish_sdk.connect(host, port, ...) and the
    SDK talks to a real BMC over HTTPS.

    In tests you use MockHttpClient to register canned responses for specific
    (method, path) pairs. This lets you test all SDK client code without a
    simulator or real hardware — fast, deterministic, and offline.

    Any path that is not registered automatically returns HTTP 404, mirroring
    how a real Redfish endpoint behaves for unknown resources.

    MockHttpClient is part of the public SDK API:
        from redfish_sdk import MockHttpClient
    """

    def test_register_at_construction(self):
        """Pre-register routes in the constructor dict."""
        mock = MockHttpClient({
            ("GET", "/redfish/v1"): _ok({"RedfishVersion": "1.6.0"}),
        })
        raw = asyncio.run(mock.request_async("GET", "/redfish/v1"))
        assert raw.status_code == 200
        assert raw.body_json["RedfishVersion"] == "1.6.0"

    def test_register_at_runtime(self):
        """Add routes dynamically with mock.register()."""
        mock = MockHttpClient()
        mock.register("GET", "/redfish/v1/Systems", _ok({"Members": []}))
        raw = asyncio.run(mock.request_async("GET", "/redfish/v1/Systems"))
        assert raw.status_code == 200
        assert raw.body_json["Members"] == []

    def test_unregistered_path_returns_404(self):
        """Any path not in the mock returns 404 — no exception raised."""
        mock = MockHttpClient()
        raw = asyncio.run(mock.request_async("GET", "/no/such/path"))
        assert raw.status_code == 404

    def test_different_methods_are_independent(self):
        """GET /uri and POST /uri are separate route entries."""
        mock = MockHttpClient({
            ("GET",  "/redfish/v1/Sessions"): _ok({"Members": []}),
            ("POST", "/redfish/v1/Sessions"): _created({"Token": "abc123"}),
        })
        get_raw  = asyncio.run(mock.request_async("GET",  "/redfish/v1/Sessions"))
        post_raw = asyncio.run(mock.request_async("POST", "/redfish/v1/Sessions"))
        assert get_raw.status_code  == 200
        assert post_raw.status_code == 201

    def test_sync_and_async_behave_identically(self):
        """MockHttpClient supports both sync and async callers."""
        mock = MockHttpClient({("GET", "/ping"): _ok({"ok": True})})
        sync_raw  = mock.request("GET", "/ping")
        async_raw = asyncio.run(mock.request_async("GET", "/ping"))
        assert sync_raw.status_code == async_raw.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Concept 2: Direct Requests
# ─────────────────────────────────────────────────────────────────────────────


class TestDirectRequests:
    """
    CONCEPT: ctx.get() / post() / patch() / delete()

    Once connected, ClientContext exposes four methods for direct HTTP access.
    Use these when a resource is not covered by a service handle, or when you
    need fine-grained control over the request body.

    All four methods return a RedfishResponse object — they never raise on
    4xx or 5xx status codes. Only infrastructure failures (network down, TLS
    error, auth rejected) raise exceptions.
    """

    def test_get_reads_a_resource(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1/Systems/1"): _ok({
                "@odata.id": "/redfish/v1/Systems/1",
                "Model": "ProLiant DL380",
                "MemorySummary": {"TotalSystemMemoryGiB": 128},
            }),
        })
        response = ctx.get("/redfish/v1/Systems/1")
        assert response.status_code == 200
        assert response.success
        assert response.body["Model"] == "ProLiant DL380"
        assert response.body["MemorySummary"]["TotalSystemMemoryGiB"] == 128

    def test_post_triggers_an_action(self):
        ctx, _ = _make_ctx({
            ("POST", "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset"): _ok(
                {"success": True}
            ),
        })
        response = ctx.post(
            "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset",
            body={"ResetType": "ForceRestart"},
        )
        assert response.status_code == 200
        assert response.success

    def test_patch_updates_a_resource(self):
        ctx, _ = _make_ctx({
            ("PATCH", "/redfish/v1/Systems/1/Bios/Settings"): _ok({
                "@odata.id": "/redfish/v1/Systems/1/Bios/Settings",
            }),
        })
        response = ctx.patch(
            "/redfish/v1/Systems/1/Bios/Settings",
            body={"Attributes": {"ProcHyperthreading": "Enabled"}},
        )
        assert response.status_code == 200
        assert response.success

    def test_delete_removes_a_resource(self):
        ctx, _ = _make_ctx({
            ("DELETE", "/redfish/v1/EventService/Subscriptions/5"): _no_content(),
        })
        response = ctx.delete("/redfish/v1/EventService/Subscriptions/5")
        assert response.status_code == 204
        assert response.success

    def test_404_is_a_response_not_an_exception(self):
        """
        In Redfish, 404 means 'resource does not exist' — it is NOT an error.
        The SDK returns RedfishResponse(success=False). Your code decides what
        to do. Only infrastructure failures raise exceptions.
        """
        ctx, _ = _make_ctx()   # empty mock — every path returns 404
        response = ctx.get("/redfish/v1/Systems/99")
        assert response.status_code == 404
        assert not response.success   # False, but no exception raised


# ─────────────────────────────────────────────────────────────────────────────
# Concept 3: RedfishResponse
# ─────────────────────────────────────────────────────────────────────────────


class TestResponseModel:
    """
    CONCEPT: RedfishResponse

    Every SDK call returns a RedfishResponse. Key fields:

        response.status_code   — HTTP status (200, 201, 202, 404, ...)
        response.success       — True if 2xx, False otherwise
        response.body          — parsed JSON dict ({} if no body)
        response.task          — RedfishTask if status_code == 202 (background job)
        response.extended_info — list of RedfishMessage from @Message.ExtendedInfo

    The 202 Accepted case is special: the BMC accepted the request but is
    doing the work asynchronously (e.g. firmware update, config change).
    Check response.task and call task.wait() to poll until completion.
    """

    def test_success_is_true_for_2xx(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1"): _ok({"RedfishVersion": "1.6.0"}),
        })
        r = ctx.get("/redfish/v1")
        assert r.success
        assert r.status_code == 200

    def test_success_is_false_for_4xx(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1/Missing"): _not_found(),
        })
        r = ctx.get("/redfish/v1/Missing")
        assert not r.success
        assert r.status_code == 404

    def test_body_contains_parsed_json(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1/Chassis/1"): _ok({
                "PowerState": "On",
                "Thermal": {"@odata.id": "/redfish/v1/Chassis/1/Thermal"},
            }),
        })
        r = ctx.get("/redfish/v1/Chassis/1")
        assert r.body["PowerState"] == "On"
        assert r.body["Thermal"]["@odata.id"] == "/redfish/v1/Chassis/1/Thermal"

    def test_202_response_has_location_header(self):
        """
        202 Accepted means the BMC started a background job and returned a
        Location header pointing to the task URI.

        Direct ctx.post() gives you the raw 202 response. To get a RedfishTask
        object that you can call .wait() on, use a service handle:
            ctx.update_service.push_firmware(path)  # returns response.task
            ctx.update_service.simple_update(uri)   # returns response.task
        """
        ctx, mock = _make_ctx()
        mock.register(
            "POST",
            "/redfish/v1/UpdateService/Actions/SimpleUpdate",
            _accepted("/redfish/v1/TaskService/Tasks/42"),
        )
        r = ctx.post(
            "/redfish/v1/UpdateService/Actions/SimpleUpdate",
            body={"ImageURI": "http://fileserver/firmware.bin"},
        )
        assert r.status_code == 202
        assert r.success   # 202 is a success code
        # Task URI is in the Location header
        assert r.headers.get("location") == "/redfish/v1/TaskService/Tasks/42"


# ─────────────────────────────────────────────────────────────────────────────
# Concept 4: ConnectionConfig — use_tls vs verify_tls
# ─────────────────────────────────────────────────────────────────────────────


class TestConnectionConfig:
    """
    CONCEPT: ConnectionConfig — use_tls and verify_tls

    Two separate settings control TLS behaviour:

        use_tls=True  (default) — connect over HTTPS
        use_tls=False           — connect over plain HTTP
                                  (simulators, some lab setups)

        verify_tls=True  (default) — reject self-signed / unknown CA certs
        verify_tls=False           — accept any cert (dev / simulator only)

    Common error: "SSL: WRONG_VERSION_NUMBER"
        Cause: use_tls=True but the server speaks plain HTTP
        Fix:   ConnectionConfig(use_tls=False)
        CLI:   python sample.py --no-tls

    Common error: "SSL: CERTIFICATE_VERIFY_FAILED"
        Cause: the BMC has a self-signed cert
        Fix:   ConnectionConfig(verify_tls=False)
        OR:    ConnectionConfig(tls_ca_cert="/path/to/bmc-ca.crt")
        CLI:   python sample.py --no-tls-verify

    Production rule: never use verify_tls=False in production.
    Always provide a proper CA cert bundle.
    """

    def test_defaults_are_secure(self):
        cfg = ConnectionConfig()
        assert cfg.use_tls is True
        assert cfg.verify_tls is True

    def test_plain_http_for_simulator(self):
        """Standard config for bmc-redfish-simulator or any plain-HTTP server."""
        cfg = ConnectionConfig(use_tls=False)
        assert cfg.use_tls is False
        # verify_tls is ignored when use_tls=False
        assert cfg.verify_tls is True

    def test_https_with_self_signed_cert(self):
        """For real BMCs in a lab with self-signed certificates."""
        cfg = ConnectionConfig(use_tls=True, verify_tls=False)
        assert cfg.use_tls is True
        assert cfg.verify_tls is False

    def test_https_with_custom_ca_bundle(self):
        """Production: provide your datacenter CA cert bundle."""
        cfg = ConnectionConfig(
            use_tls=True,
            verify_tls=True,
            tls_ca_cert="/etc/ssl/certs/datacenter-ca.crt",
        )
        assert cfg.tls_ca_cert == "/etc/ssl/certs/datacenter-ca.crt"

    def test_timeout_overrides(self):
        """Increase timeouts for slow BMCs or high-latency networks."""
        cfg = ConnectionConfig(
            connect_timeout_sec=30.0,
            request_timeout_sec=120.0,
            task_timeout_sec=600.0,
        )
        assert cfg.connect_timeout_sec == 30.0
        assert cfg.request_timeout_sec == 120.0


# ─────────────────────────────────────────────────────────────────────────────
# Concept 5: Discovery
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscovery:
    """
    CONCEPT: ctx.discover() / ctx.discovery

    The Redfish service root (/redfish/v1) lists every service the BMC exposes.
    The SDK walks it and returns a DiscoveryResult — a map of service names
    to their URIs.

    Three modes:
        ctx.discover()                — full: all known service keys
        ctx.discover(root_only=True)  — enumerate root keys without traversal
        ctx.discover("EventService")  — partial: locate one specific service

    connect() calls full discovery internally. You only need to call
    discover() explicitly if you want to inspect what's available before
    deciding what to do next.
    """

    _SERVICE_ROOT = {
        "@odata.id": "/redfish/v1",
        "RedfishVersion": "1.6.0",
        "Systems":          {"@odata.id": "/redfish/v1/Systems"},
        "Chassis":          {"@odata.id": "/redfish/v1/Chassis"},
        "Managers":         {"@odata.id": "/redfish/v1/Managers"},
        "EventService":     {"@odata.id": "/redfish/v1/EventService"},
        "TelemetryService": {"@odata.id": "/redfish/v1/TelemetryService"},
        "UpdateService":    {"@odata.id": "/redfish/v1/UpdateService"},
    }

    def test_full_discovery_finds_all_services(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1"): _ok(self._SERVICE_ROOT),
        })
        result = ctx.discover()
        assert result.has_service("Systems")
        assert result.has_service("EventService")
        assert result.has_service("UpdateService")
        assert result.service_uri("Systems") == "/redfish/v1/Systems"

    def test_partial_discovery_finds_one_service(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1"): _ok(self._SERVICE_ROOT),
        })
        result = ctx.discover("EventService")
        assert result.has_service("EventService")
        # partial mode: only the requested service is in the result
        assert not result.has_service("Systems")

    def test_missing_service_returns_false_not_exception(self):
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1"): _ok(self._SERVICE_ROOT),
        })
        result = ctx.discover()
        assert not result.has_service("NonExistentService")
        assert result.service_uri("NonExistentService") is None

    def test_discovery_populates_context_discovery_map(self):
        """
        As a side effect, discover() fills ctx._discovery_map.
        Service handles (event_service, log_service, etc.) read from this map
        to resolve URIs without making extra network requests.
        This is why you should call discover() before using service handles.
        """
        ctx, _ = _make_ctx({
            ("GET", "/redfish/v1"): _ok(self._SERVICE_ROOT),
        })
        ctx.discover()
        assert ctx._discovery_map["EventService"]     == "/redfish/v1/EventService"
        assert ctx._discovery_map["TelemetryService"] == "/redfish/v1/TelemetryService"


# ─────────────────────────────────────────────────────────────────────────────
# Concept 6: Event Subscriptions
# ─────────────────────────────────────────────────────────────────────────────


class TestEventService:
    """
    CONCEPT: ctx.event_service

    Redfish event subscriptions tell the BMC to push events to your listener
    endpoint. Typical flow:

        1. Start a RedfishEventListener on a local port (see sample 06)
        2. Call ctx.event_service.subscribe(destination=...) with your URL
        3. The BMC POSTs JSON event payloads to your URL as they occur
        4. Call delete_subscription() when done to avoid orphaned subscriptions

    Subscription properties:
        destination         — your listener URL (required)
        event_types         — legacy filter: ["Alert", "StatusChange", ...]
        registry_prefixes   — modern filter: ["TaskEvent", "ResourceEvent", ...]
        message_ids         — filter to specific message IDs
        context             — free-form tag echoed back in each event
    """

    def _make_event_svc(self, routes: dict) -> EventServiceHandle:
        mock = MockHttpClient(routes)
        return EventServiceHandle(
            http=mock,
            auth_state=_auth_state(),
            discovery_map={"EventService": "/redfish/v1/EventService"},
        )

    def test_subscribe_creates_a_subscription(self):
        svc = self._make_event_svc({
            ("POST", "/redfish/v1/EventService/Subscriptions"): _created(
                {"@odata.id": "/redfish/v1/EventService/Subscriptions/1"},
                location="/redfish/v1/EventService/Subscriptions/1",
            ),
        })
        response = svc.subscribe(
            destination="http://my-listener:9090",
            event_types=["Alert", "StatusChange"],
            context="my-app-tag",
        )
        assert response.status_code == 201
        assert response.success
        assert response.body["@odata.id"].endswith("/1")

    def test_subscribe_with_registry_prefixes(self):
        """
        Use registry_prefixes for modern Redfish 1.6+ endpoints.
        RegistryPrefixes filter events to a message registry
        (e.g. "TaskEvent", "ResourceEvent", vendor-specific).
        """
        svc = self._make_event_svc({
            ("POST", "/redfish/v1/EventService/Subscriptions"): _created(
                {"@odata.id": "/redfish/v1/EventService/Subscriptions/2"},
            ),
        })
        response = svc.subscribe(
            destination="http://my-listener:9090",
            registry_prefixes=["TaskEvent", "ResourceEvent"],
        )
        assert response.success

    def test_list_subscriptions_returns_members(self):
        svc = self._make_event_svc({
            ("GET", "/redfish/v1/EventService/Subscriptions"): _ok({
                "Members": [
                    {"@odata.id": "/redfish/v1/EventService/Subscriptions/1"},
                    {"@odata.id": "/redfish/v1/EventService/Subscriptions/2"},
                ],
                "Members@odata.count": 2,
            }),
        })
        response = svc.list_subscriptions()
        assert response.success
        assert len(response.body["Members"]) == 2

    def test_delete_subscription(self):
        svc = self._make_event_svc({
            ("DELETE", "/redfish/v1/EventService/Subscriptions/1"): _no_content(),
        })
        response = svc.delete_subscription(
            "/redfish/v1/EventService/Subscriptions/1"
        )
        assert response.status_code == 204
        assert response.success

    def test_missing_subscription_returns_404_not_exception(self):
        svc = self._make_event_svc({})   # empty mock — everything 404
        response = svc.get_subscription(
            "/redfish/v1/EventService/Subscriptions/999"
        )
        assert response.status_code == 404
        assert not response.success


# ─────────────────────────────────────────────────────────────────────────────
# Concept 7: Log Service
# ─────────────────────────────────────────────────────────────────────────────


class TestLogService:
    """
    CONCEPT: ctx.log_service

    Redfish LogServices store event records and SEL (System Event Log) data.
    They live under each System and Manager — a BMC can have several.

    Key methods:
        list_services()                        — find all log services on the BMC
        get_entries(log_service_uri)           — all entries in a log
        get_entries(uri, filter=LogFilter(...))— filtered entries

    LogFilter parameters:
        top=N              — return first N entries ($top)
        skip=N             — skip first N entries ($skip) — use for pagination
        severity="Critical"— filter by severity level ($filter)
        message_id="X0001" — filter by message ID ($filter)
    """

    def _make_log_svc(self, routes: dict) -> LogServiceHandle:
        mock = MockHttpClient(routes)
        return LogServiceHandle(
            http=mock,
            auth_state=_auth_state(),
            discovery_map={},
        )

    def test_get_entries_returns_all_log_entries(self):
        svc = self._make_log_svc({
            ("GET", "/redfish/v1/Systems/1/LogServices/Log1/Entries"): _ok({
                "Members": [
                    {"Id": "1", "Severity": "OK",       "Message": "System started"},
                    {"Id": "2", "Severity": "Warning",  "Message": "Fan speed reduced"},
                    {"Id": "3", "Severity": "Critical", "Message": "CPU temperature exceeded"},
                ],
                "Members@odata.count": 3,
            }),
        })
        response = svc.get_entries("/redfish/v1/Systems/1/LogServices/Log1")
        assert response.success
        assert len(response.body["Members"]) == 3

    def test_get_entries_with_top_filter(self):
        """LogFilter.top adds ?$top=N to the request."""
        svc = self._make_log_svc({
            ("GET", "/redfish/v1/Systems/1/LogServices/Log1/Entries?$top=2"): _ok({
                "Members": [
                    {"Id": "1", "Severity": "OK",      "Message": "System started"},
                    {"Id": "2", "Severity": "Warning", "Message": "Fan speed reduced"},
                ],
                "Members@odata.count": 2,
            }),
        })
        response = svc.get_entries(
            "/redfish/v1/Systems/1/LogServices/Log1",
            filter=LogFilter(top=2),
        )
        assert response.success
        assert len(response.body["Members"]) == 2

    def test_get_entries_with_skip_for_pagination(self):
        """Use skip + top together to page through large logs."""
        svc = self._make_log_svc({
            ("GET", "/redfish/v1/Systems/1/LogServices/Log1/Entries?$skip=10&$top=10"): _ok({
                "Members": [{"Id": str(i)} for i in range(11, 21)],
                "Members@odata.count": 10,
            }),
        })
        response = svc.get_entries(
            "/redfish/v1/Systems/1/LogServices/Log1",
            filter=LogFilter(skip=10, top=10),
        )
        assert response.success
        assert response.body["Members"][0]["Id"] == "11"

    def test_list_services_aggregates_across_systems_and_managers(self):
        """
        list_services() walks both /Systems and /Managers to find all log
        services. A typical server has at least two: one System log, one
        BMC/Manager log.
        """
        mock = MockHttpClient({
            ("GET", "/redfish/v1/Systems"): _ok({
                "Members": [{"@odata.id": "/redfish/v1/Systems/1"}],
            }),
            ("GET", "/redfish/v1/Systems/1/LogServices"): _ok({
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/1/LogServices/Log1"},
                ],
            }),
            ("GET", "/redfish/v1/Managers"): _ok({
                "Members": [{"@odata.id": "/redfish/v1/Managers/BMC"}],
            }),
            ("GET", "/redfish/v1/Managers/BMC/LogServices"): _ok({
                "Members": [
                    {"@odata.id": "/redfish/v1/Managers/BMC/LogServices/BMCLog"},
                ],
            }),
        })
        svc = LogServiceHandle(http=mock, auth_state=_auth_state(), discovery_map={})
        response = svc.list_services()
        assert response.success
        uris = [m["@odata.id"] for m in response.body["Members"]]
        assert "/redfish/v1/Systems/1/LogServices/Log1" in uris
        assert "/redfish/v1/Managers/BMC/LogServices/BMCLog" in uris


# ─────────────────────────────────────────────────────────────────────────────
# Concept 8: Error Handling
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """
    CONCEPT: When does the SDK raise vs return?

    RULE: HTTP status codes (4xx, 5xx) ALWAYS return as RedfishResponse.
          They never raise exceptions.

    Exceptions are raised only for infrastructure failures:
        RedfishConnectionError  — host unreachable, port closed
        RedfishTLSError         — TLS certificate / handshake failure
        RedfishAuthError        — wrong credentials, session rejected by BMC
        RedfishProtocolError    — BMC returned malformed Redfish (e.g. non-JSON)
        RedfishHTTPError        — raised by SDK code for invalid arguments
        RedfishTaskFailedError  — task.wait() and BMC reported task failure
        RedfishTaskTimeoutError — task.wait() timed out

    All exceptions inherit from RedfishSDKError — catch it for a single handler.

    The pattern:
        r = ctx.get(uri)
        if not r.success:
            log.warning("not found: %s", uri)   # not an exception

        try:
            ctx = redfish_sdk.connect(host, port, creds)
        except RedfishConnectionError:
            sys.exit("BMC unreachable")
    """

    def test_404_is_a_response_not_an_exception(self):
        ctx, _ = _make_ctx()
        r = ctx.get("/redfish/v1/Systems/999")
        assert r.status_code == 404
        assert not r.success   # informational, not exceptional

    def test_500_is_a_response_not_an_exception(self):
        ctx, mock = _make_ctx()
        body = {"error": {"message": "Internal Server Error"}}
        mock.register(
            "GET", "/redfish/v1/Chassis",
            RawHttpResponse(500, {}, json.dumps(body), body),
        )
        r = ctx.get("/redfish/v1/Chassis")
        assert r.status_code == 500
        assert not r.success   # still not an exception

    def test_protocol_error_if_service_root_not_json(self):
        """
        Discovery raises RedfishProtocolError if /redfish/v1 doesn't return
        a valid JSON object. This means you connected to a non-Redfish server
        or the wrong port.
        """
        ctx, mock = _make_ctx()
        # body_json=None signals that the response body was not valid JSON
        mock.register(
            "GET", "/redfish/v1",
            RawHttpResponse(200, {}, "<html>Not Redfish</html>", None),
        )
        with pytest.raises(RedfishProtocolError):
            ctx.discover()

    def test_all_sdk_exceptions_share_base_class(self):
        """Catch RedfishSDKError to handle all SDK errors in one place."""
        from redfish_sdk import (
            RedfishConnectionError,
            RedfishTLSError,
            RedfishAuthError,
            RedfishProtocolError,
            RedfishHTTPError,
        )
        for exc_cls in (
            RedfishConnectionError,
            RedfishTLSError,
            RedfishAuthError,
            RedfishProtocolError,
            RedfishHTTPError,
        ):
            assert issubclass(exc_cls, RedfishSDKError), (
                f"{exc_cls.__name__} must inherit from RedfishSDKError"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Concept 9: The Full Context — putting it all together
# ─────────────────────────────────────────────────────────────────────────────


class TestFullContext:
    """
    CONCEPT: Using ClientContext as a unified handle

    In real code, connect() returns a ClientContext. You keep it for the full
    session. Service handles are lazily initialised on first access.

    This class shows how to wire up the full context against mock responses
    to write integration-style tests for your own application code.
    The pattern mirrors exactly what you would write in production, with
    MockHttpClient replacing the live BMC.
    """

    def _build_routes(self) -> dict:
        return {
            ("GET", "/redfish/v1"): _ok({
                "RedfishVersion": "1.6.0",
                "Systems":      {"@odata.id": "/redfish/v1/Systems"},
                "Chassis":      {"@odata.id": "/redfish/v1/Chassis"},
                "Managers":     {"@odata.id": "/redfish/v1/Managers"},
                "EventService": {"@odata.id": "/redfish/v1/EventService"},
            }),
            ("GET", "/redfish/v1/Systems"): _ok({
                "Members": [{"@odata.id": "/redfish/v1/Systems/1"}],
                "Members@odata.count": 1,
            }),
            ("GET", "/redfish/v1/Systems/1"): _ok({
                "Id": "1",
                "Model": "PowerEdge R750",
                "PowerState": "On",
                "MemorySummary": {"TotalSystemMemoryGiB": 256},
            }),
            ("GET", "/redfish/v1/EventService"): _ok({
                "Id": "EventService",
                "Subscriptions": {
                    "@odata.id": "/redfish/v1/EventService/Subscriptions",
                },
            }),
            ("GET", "/redfish/v1/EventService/Subscriptions"): _ok({
                "Members": [],
                "Members@odata.count": 0,
            }),
        }

    def test_discover_then_walk_systems(self):
        """The most common pattern: discover → list collection → get member."""
        ctx, _ = _make_ctx(self._build_routes())

        result = ctx.discover()
        assert result.has_service("Systems")

        # List all systems
        systems = ctx.get(result.service_uri("Systems"))
        assert systems.success
        first_system_uri = systems.body["Members"][0]["@odata.id"]

        # Get the first system
        system = ctx.get(first_system_uri)
        assert system.body["Model"] == "PowerEdge R750"
        assert system.body["PowerState"] == "On"

    def test_service_handles_are_lazily_created(self):
        """
        ctx.event_service, ctx.log_service, etc. are only created on first
        access. Multiple accesses return the same cached instance.
        """
        ctx, _ = _make_ctx(self._build_routes())
        handle_a = ctx.event_service
        handle_b = ctx.event_service
        assert handle_a is handle_b   # same object — lazy singleton

    def test_event_service_uses_discovery_map_uri(self):
        """
        After discover(), event_service reads its URI from the discovery map
        instead of using the default /redfish/v1/EventService hardcode.
        Call discover() first to ensure service handles resolve correctly on
        non-standard BMC URI layouts.
        """
        ctx, _ = _make_ctx(self._build_routes())
        ctx.discover()
        assert ctx._discovery_map.get("EventService") == "/redfish/v1/EventService"

        info = ctx.event_service.get_service_info()
        assert info.success

    def test_is_connected_flag(self):
        ctx, _ = _make_ctx()
        assert ctx.is_connected is True

    def test_use_tls_false_config_is_stored(self):
        """
        ctx._config holds the ConnectionConfig passed at construction.
        Inspect it to verify use_tls and other settings are correct.
        """
        ctx, _ = _make_ctx()
        # _make_ctx() passes ConnectionConfig(use_tls=False)
        assert ctx._config.use_tls is False
