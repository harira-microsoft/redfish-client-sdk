"""
redfish_sdk/errors.py

SDK exception hierarchy.
All exceptions derive from RedfishSDKError.
"""

from __future__ import annotations


class RedfishSDKError(Exception):
    """Base class for all SDK exceptions."""


class RedfishConnectionError(RedfishSDKError):
    """TCP / network failure."""


class RedfishTLSError(RedfishSDKError):
    """TLS certificate or handshake failure."""


class RedfishAuthError(RedfishSDKError):
    """Authentication rejected by the endpoint (401 / 403 / session failure)."""


class RedfishProtocolError(RedfishSDKError):
    """Endpoint is not Redfish-compliant."""


class RedfishHTTPError(RedfishSDKError):
    """Unexpected HTTP-level error (not surfaced as RedfishResponse)."""

    def __init__(self, message: str, status_code: int, response: object = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RedfishTaskTimeoutError(RedfishSDKError):
    """Task did not reach a terminal state within the configured timeout."""

    def __init__(self, message: str, task: object = None) -> None:
        super().__init__(message)
        self.task = task


class RedfishTaskFailedError(RedfishSDKError):
    """Task reached a failed terminal state (Exception / Killed)."""

    def __init__(self, message: str, task: object = None) -> None:
        super().__init__(message)
        self.task = task
