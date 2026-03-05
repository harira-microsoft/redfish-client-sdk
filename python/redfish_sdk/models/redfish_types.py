"""
redfish_sdk/models/redfish_types.py

Pure data types shared across the SDK.
No imports from other SDK modules.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class AuthMode(Enum):
    SESSION = "session"
    STATELESS = "stateless"


@dataclass
class Credentials:
    username: str
    password: str

    def as_basic_header(self) -> str:
        token = base64.b64encode(
            f"{self.username}:{self.password}".encode()
        ).decode()
        return f"Basic {token}"

    def __repr__(self) -> str:
        return f"Credentials(username={self.username!r}, password=***)"


# ---------------------------------------------------------------------------
# Connection config
# ---------------------------------------------------------------------------

@dataclass
class ConnectionConfig:
    verify_tls: bool = True
    tls_ca_cert: str | None = None
    connect_timeout_sec: float = 10.0
    request_timeout_sec: float = 30.0
    task_poll_interval_sec: float = 5.0
    task_timeout_sec: float = 300.0
    base_path_override: str | None = None


# ---------------------------------------------------------------------------
# Internal — TLS
# ---------------------------------------------------------------------------

@dataclass
class TLSConfig:
    # passed directly to httpx as the `verify` argument
    verify: bool | str = True       # False | True | path-to-CA-cert


# ---------------------------------------------------------------------------
# Internal — Timeouts
# ---------------------------------------------------------------------------

@dataclass
class TimeoutConfig:
    connect_sec: float = 10.0
    request_sec: float = 30.0
    task_poll_sec: float = 5.0
    task_timeout_sec: float = 300.0


# ---------------------------------------------------------------------------
# Internal — Endpoint capabilities
# ---------------------------------------------------------------------------

@dataclass
class EndpointCapabilities:
    redfish_version: str = ""
    odata_version: str = "4.0"
    short_form: bool = True
    base_path: str = "/redfish/v1"
    available_services: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal — Auth state
# ---------------------------------------------------------------------------

@dataclass
class AuthState:
    mode: AuthMode = AuthMode.STATELESS
    session_token: str | None = None
    session_uri: str | None = None
    credentials: Credentials | None = None


# ---------------------------------------------------------------------------
# Internal — raw HTTP response (transport ↔ protocol boundary)
# ---------------------------------------------------------------------------

@dataclass
class RawHttpResponse:
    status_code: int
    headers: dict[str, str]
    body_text: str
    body_json: dict | list | None = None
