# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk — Python SDK for Redfish-compliant endpoints.

Public API surface:
    connect()               — sync connection, returns ClientContext
    connect_async()         — async connection, returns ClientContext
    RedfishEventListener    — standalone push-event receiver
    Credentials             — username + password container
    AuthMode                — SESSION or STATELESS
    ConnectionConfig        — optional overrides for TLS, timeouts
    RedfishSDKError         — base exception
    (all sub-exceptions)
"""

from redfish_sdk.client import connect, connect_async
from redfish_sdk.context import ClientContext
from redfish_sdk.errors import (
    RedfishAuthError,
    RedfishConnectionError,
    RedfishHTTPError,
    RedfishProtocolError,
    RedfishSDKError,
    RedfishTaskFailedError,
    RedfishTaskTimeoutError,
    RedfishTLSError,
)
from redfish_sdk.events.listener import RedfishEventListener
from redfish_sdk.models.redfish_types import AuthMode, ConnectionConfig, Credentials
from redfish_sdk.protocol.response import RedfishMessage, RedfishResponse
from redfish_sdk.protocol.task import RedfishTask, TaskState
from redfish_sdk.services.event_service import RedfishEvent
from redfish_sdk.services.log_service import ParsedSelRecord, parse_sel_entry
from redfish_sdk.services.ras_service import (
    CperSeverity,
    RasEndpoint,
    CperEvent,
    CpadRecord,
    RasServiceHandle,
)
from redfish_sdk.transport.http_client import MockHttpClient
from redfish_sdk.models.redfish_types import RawHttpResponse

__all__ = [
    "connect",
    "connect_async",
    "ClientContext",
    "RedfishEventListener",
    "Credentials",
    "AuthMode",
    "ConnectionConfig",
    "RedfishResponse",
    "RedfishMessage",
    "RedfishTask",
    "TaskState",
    "RedfishEvent",
    "ParsedSelRecord",
    "parse_sel_entry",
    "CperSeverity",
    "RasEndpoint",
    "CperEvent",
    "CpadRecord",
    "RasServiceHandle",
    "MockHttpClient",
    "RawHttpResponse",
    "RedfishSDKError",
    "RedfishConnectionError",
    "RedfishTLSError",
    "RedfishAuthError",
    "RedfishProtocolError",
    "RedfishHTTPError",
    "RedfishTaskTimeoutError",
    "RedfishTaskFailedError",
]
