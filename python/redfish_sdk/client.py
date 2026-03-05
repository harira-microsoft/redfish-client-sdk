"""
redfish_sdk/client.py

SDK entry point — connect() and connect_async().
Returns a ClientContext on success. Raises on failure.
Imports: context, transport, models.
"""

from __future__ import annotations

import ssl

import httpx

from redfish_sdk.context import ClientContext
from redfish_sdk.errors import RedfishAuthError, RedfishConnectionError, RedfishProtocolError, RedfishTLSError
from redfish_sdk.models.redfish_types import (
    AuthMode,
    ConnectionConfig,
    Credentials,
    EndpointCapabilities,
    TimeoutConfig,
)
from redfish_sdk.transport.auth import AuthManager
from redfish_sdk.transport.http_client import DefaultHttpClient
from redfish_sdk.transport.tls import build_tls_config

import logging
logger = logging.getLogger(__name__)


async def connect_async(
    host: str,
    port: int,
    credentials: Credentials,
    auth_mode: AuthMode,
    config: ConnectionConfig | None = None,
) -> ClientContext:
    """
    Async entry point. Establishes a connection and returns a ClientContext.
    Raises RedfishConnectionError, RedfishTLSError, RedfishAuthError,
    RedfishProtocolError on failure.
    """
    cfg = config or ConnectionConfig()
    timeouts = TimeoutConfig(
        connect_sec=cfg.connect_timeout_sec,
        request_sec=cfg.request_timeout_sec,
        task_poll_sec=cfg.task_poll_interval_sec,
        task_timeout_sec=cfg.task_timeout_sec,
    )
    tls_config = build_tls_config(cfg)
    # Always HTTPS — verify_tls controls cert verification, not the protocol.
    # (verify_tls=False = use HTTPS with unverified/self-signed cert)
    base_url = f"https://{host}:{port}"

    # Best-effort HTTP probe to /redfish/v1 for service discovery.
    # Real BMCs expose this unauthenticated endpoint over plain HTTP.
    # Non-fatal: if the server only speaks HTTPS the probe is skipped silently.
    base_path = cfg.base_path_override or "/redfish/v1"
    await _http_probe_async(host, port, base_path, timeouts.connect_sec)

    logger.debug("Connecting to %s (auth=%s)", base_url, auth_mode.value)
    http = DefaultHttpClient(base_url, tls_config, timeouts, cfg)

    try:
        auth_manager = AuthManager(http, credentials, auth_mode)
        auth_state = await auth_manager.authenticate_async()
        logger.debug("Authenticated via %s", auth_mode.value)
    except httpx.ConnectError as exc:
        await http.close_async()
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, ssl.SSLError):
            raise RedfishTLSError(f"TLS error connecting to {host}:{port} — {cause}") from exc
        raise RedfishConnectionError(f"Cannot reach {host}:{port} — {exc}") from exc
    except ssl.SSLError as exc:
        await http.close_async()
        raise RedfishTLSError(f"TLS error connecting to {host}:{port} — {exc}") from exc
    except httpx.ConnectTimeout as exc:
        await http.close_async()
        raise RedfishConnectionError(f"Connection timed out to {host}:{port}") from exc
    except RedfishAuthError:
        # SESSION auth failed (no SessionService, 404, or rejected).
        # If the caller opted in to fallback, transparently retry stateless.
        if auth_mode == AuthMode.SESSION and cfg.allow_session_fallback:
            try:
                fallback_manager = AuthManager(http, credentials, AuthMode.STATELESS)
                auth_state = await fallback_manager.authenticate_async()
            except Exception:
                await http.close_async()
                raise
        else:
            await http.close_async()
            raise

    capabilities = await _detect_capabilities_async(http, auth_state, cfg)
    logger.debug(
        "Connected to %s — Redfish %s",
        base_url, capabilities.redfish_version,
    )
    return ClientContext(
        http=http,
        auth_state=auth_state,
        capabilities=capabilities,
        config=cfg,
        timeouts=timeouts,
    )


def connect(
    host: str,
    port: int,
    credentials: Credentials,
    auth_mode: AuthMode,
    config: ConnectionConfig | None = None,
) -> ClientContext:
    """
    Sync entry point. Wraps connect_async().
    Raises if called from within a running event loop — use connect_async() instead.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        raise RuntimeError(
            "connect() cannot be called from within a running event loop. "
            "Use await connect_async() instead."
        )

    return asyncio.run(connect_async(host, port, credentials, auth_mode, config))


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

async def _http_probe_async(host: str, port: int, path: str, timeout: float) -> None:
    """
    Unauthenticated HTTP GET to /redfish/v1 for initial service discovery.
    Real BMCs serve this endpoint over plain HTTP (no credentials, no TLS).
    Non-fatal: if the server only speaks HTTPS the probe fails silently and
    the caller proceeds to the HTTPS connection.
    """
    probe_url = f"http://{host}:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as probe:
            resp = await probe.get(probe_url)
            if resp.status_code == 200 and "RedfishVersion" in resp.text:
                logger.debug("HTTP probe %s — Redfish endpoint confirmed", probe_url)
            else:
                logger.debug("HTTP probe %s returned HTTP %d", probe_url, resp.status_code)
    except Exception as exc:
        logger.debug("HTTP probe %s failed (non-fatal): %s", probe_url, exc)


async def _detect_capabilities_async(
    http: HttpClient,
    auth_state,
    config: ConnectionConfig,
) -> EndpointCapabilities:
    from redfish_sdk.transport.auth import AuthManager

    headers = AuthManager.attach_auth(auth_state, {})
    base_path = config.base_path_override or "/redfish/v1"
    raw = await http.request_async("GET", base_path, headers=headers)

    if raw.status_code != 200 or not isinstance(raw.body_json, dict):
        raise RedfishProtocolError(
            f"ServiceRoot at {base_path} returned HTTP {raw.status_code} — "
            "not a Redfish endpoint"
        )

    body = raw.body_json
    session_svc = body.get("SessionService")
    return EndpointCapabilities(
        redfish_version=body.get("RedfishVersion", ""),
        odata_version=raw.headers.get("odata-version", "4.0"),
        short_form=True,
        base_path=base_path,
        available_services=[
            k for k, v in body.items()
            if isinstance(v, dict) and "@odata.id" in v
        ],
        uuid=body.get("UUID", ""),
        product=body.get("Product", ""),
        session_service_uri=(
            session_svc.get("@odata.id")
            if isinstance(session_svc, dict)
            else None
        ),
    )
