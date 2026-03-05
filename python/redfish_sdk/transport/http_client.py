"""
redfish_sdk/transport/http_client.py

Transport abstraction layer.

  HttpClient         — abstract base (NFR8.2: injectable/mockable)
  DefaultHttpClient  — production impl: httpx, retry logic (FR1.8, FR1.9)
  MockHttpClient     — test double: canned (method, path) → RawHttpResponse

Imports: models only.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import ssl
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx

from redfish_sdk.models.redfish_types import RawHttpResponse, TimeoutConfig, TLSConfig

if TYPE_CHECKING:
    from redfish_sdk.models.redfish_types import ConnectionConfig

logger = logging.getLogger(__name__)

_REDFISH_HEADERS = {
    "OData-Version": "4.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Abstract base — NFR8.2
# ---------------------------------------------------------------------------

class HttpClient(ABC):
    """
    Abstract transport interface.  All SDK layers depend on this type.
    Use DefaultHttpClient for production; MockHttpClient for unit tests.
    """

    @abstractmethod
    async def request_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse: ...

    @abstractmethod
    async def request_multipart_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None,
        files: dict,
    ) -> RawHttpResponse:
        """Send a multipart/form-data request (FR7.5 firmware push)."""
        ...

    @abstractmethod
    async def close_async(self) -> None: ...

    @abstractmethod
    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse: ...

    @abstractmethod
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Production implementation — httpx + retry
# ---------------------------------------------------------------------------

class DefaultHttpClient(HttpClient):
    """
    Single httpx.AsyncClient / httpx.Client instance per SDK connection.
    Auth headers are NOT attached here — done by AuthManager.

    Retry behaviour (FR1.8, FR1.9):
      - On connection error (ConnectError/ConnectTimeout): up to
        retry_on_connection_failure extra attempts.
      - On a matching HTTP status code in retry_status_codes: same count.
      - retry_delay_sec seconds sleep between attempts.
    """

    def __init__(
        self,
        base_url: str,
        tls_config: TLSConfig,
        timeouts: TimeoutConfig,
        config: "ConnectionConfig | None" = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=timeouts.connect_sec,
            read=timeouts.request_sec,
            write=timeouts.request_sec,
            pool=timeouts.request_sec,
        )
        self._verify = tls_config.verify
        if config is not None:
            self._retry_count = max(0, config.retry_on_connection_failure)
            self._retry_status_codes: frozenset[int] = frozenset(config.retry_status_codes)
            self._retry_delay = max(0.0, config.retry_delay_sec)
        else:
            self._retry_count = 0
            self._retry_status_codes = frozenset()
            self._retry_delay = 2.0
        self._async_client: httpx.AsyncClient | None = None
        self._sync_client: httpx.Client | None = None

    # -----------------------------------------------------------------------
    # Async
    # -----------------------------------------------------------------------

    async def request_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        merged = {**_REDFISH_HEADERS, **(headers or {})}
        content = _json.dumps(body).encode() if body is not None else None
        last_exc: Exception | None = None
        last_response: RawHttpResponse | None = None

        for attempt in range(self._retry_count + 1):
            if attempt > 0:
                logger.debug(
                    "Retry %d/%d for %s %s after %.1fs",
                    attempt, self._retry_count, method, path, self._retry_delay,
                )
                await asyncio.sleep(self._retry_delay)
            try:
                client = await self._get_async_client()
                response = await client.request(
                    method=method, url=path, headers=merged, content=content,
                )
                raw = _to_raw(response)
                if raw.status_code in self._retry_status_codes and attempt < self._retry_count:
                    logger.debug(
                        "HTTP %d in retry_status_codes; retrying (%d left)",
                        raw.status_code, self._retry_count - attempt,
                    )
                    last_response = raw
                    continue
                logger.debug("%s %s -> HTTP %d", method, path, raw.status_code)
                return raw
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # SSL errors (e.g. connecting http:// to an https endpoint) must
                # never be retried — propagate immediately so the caller can
                # raise a meaningful TLS error.
                cause = exc.__cause__ or exc.__context__
                if isinstance(cause, ssl.SSLError) or isinstance(exc.__context__, ssl.SSLError):
                    raise
                exc_str = str(exc).lower()
                if "ssl" in exc_str or "wrong version" in exc_str or "tls" in exc_str:
                    raise
                logger.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt + 1, self._retry_count + 1, exc,
                )
                last_exc = exc

        if last_exc is not None:
            logger.error(
                "All %d connection attempt(s) failed for %s %s",
                self._retry_count + 1, method, path,
            )
            return RawHttpResponse(
                status_code=503,
                headers={},
                body_text=str(last_exc),
                body_json={"error": {"message": str(last_exc)}},
            )
        return last_response or RawHttpResponse(
            status_code=503, headers={}, body_text="Unknown error", body_json={}
        )

    async def request_multipart_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None,
        files: dict,
    ) -> RawHttpResponse:
        merged = {k: v for k, v in (headers or {}).items()}
        # Remove Content-Type — httpx sets multipart/form-data with boundary automatically
        merged.pop("Content-Type", None)
        merged.pop("content-type", None)
        try:
            client = await self._get_async_client()
            response = await client.request(
                method=method, url=path, headers=merged, files=files,
            )
        except httpx.RemoteProtocolError as exc:
            logger.error("Multipart %s %s failed: %s", method, path, exc)
            return RawHttpResponse(
                status_code=503, headers={}, body_text=str(exc),
                body_json={"error": {"message": str(exc)}},
            )
        logger.debug("Multipart %s %s -> HTTP %d", method, path, response.status_code)
        return _to_raw(response)

    async def close_async(self) -> None:
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url,
                verify=self._verify,
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._async_client

    # -----------------------------------------------------------------------
    # Sync
    # -----------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        import time
        merged = {**_REDFISH_HEADERS, **(headers or {})}
        content = _json.dumps(body).encode() if body is not None else None
        last_exc: Exception | None = None
        last_response: RawHttpResponse | None = None

        for attempt in range(self._retry_count + 1):
            if attempt > 0:
                logger.debug(
                    "Retry %d/%d for %s %s after %.1fs",
                    attempt, self._retry_count, method, path, self._retry_delay,
                )
                time.sleep(self._retry_delay)
            try:
                client = self._get_sync_client()
                response = client.request(
                    method=method, url=path, headers=merged, content=content,
                )
                raw = _to_raw(response)
                if raw.status_code in self._retry_status_codes and attempt < self._retry_count:
                    last_response = raw
                    continue
                return raw
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                cause = exc.__cause__ or exc.__context__
                if isinstance(cause, ssl.SSLError) or isinstance(exc.__context__, ssl.SSLError):
                    raise
                exc_str = str(exc).lower()
                if "ssl" in exc_str or "wrong version" in exc_str or "tls" in exc_str:
                    raise
                logger.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt + 1, self._retry_count + 1, exc,
                )
                last_exc = exc

        if last_exc is not None:
            return RawHttpResponse(
                status_code=503, headers={}, body_text=str(last_exc),
                body_json={"error": {"message": str(last_exc)}},
            )
        return last_response or RawHttpResponse(
            status_code=503, headers={}, body_text="Unknown error", body_json={}
        )

    def close(self) -> None:
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self._base_url,
                verify=self._verify,
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._sync_client


# ---------------------------------------------------------------------------
# Test double — NFR8.2
# ---------------------------------------------------------------------------

class MockHttpClient(HttpClient):
    """
    In-memory transport for unit tests.  No network, no BMC required.

    Responses are keyed by (METHOD_UPPER, path).  Unregistered paths return
    HTTP 404.  Register multipart responses under the same key as POST.

    Example::

        mock = MockHttpClient({
            ("GET", "/redfish/v1"):
                RawHttpResponse(200, {}, '{"RedfishVersion":"1.6.0"}',
                                {"RedfishVersion": "1.6.0"}),
        })
    """

    def __init__(
        self, responses: dict[tuple[str, str], RawHttpResponse] | None = None
    ) -> None:
        self._responses: dict[tuple[str, str], RawHttpResponse] = responses or {}

    def register(self, method: str, path: str, response: RawHttpResponse) -> None:
        """Register or replace a canned response at runtime."""
        self._responses[(method.upper(), path)] = response

    def _lookup(self, method: str, path: str) -> RawHttpResponse:
        key = (method.upper(), path)
        if key in self._responses:
            logger.debug("MockHttpClient hit: %s %s", method, path)
            return self._responses[key]
        logger.debug("MockHttpClient miss: %s %s -> 404", method, path)
        return RawHttpResponse(
            status_code=404,
            headers={},
            body_text="Not Found",
            body_json={"error": {"message": f"MockHttpClient: no response for {method} {path}"}},
        )

    async def request_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        return self._lookup(method, path)

    async def request_multipart_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None,
        files: dict,
    ) -> RawHttpResponse:
        return self._lookup(method, path)

    async def close_async(self) -> None:
        pass

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        return self._lookup(method, path)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_raw(response: httpx.Response) -> RawHttpResponse:
    headers = dict(response.headers.items())
    body_text = response.text
    body_json: dict | list | None = None
    content_type = headers.get("content-type", "")
    if "application/json" in content_type or "odata" in content_type:
        try:
            body_json = response.json()
        except Exception:
            pass
    # For responses with no parseable body (e.g. 204 No Content), fall back to
    # an empty dict so callers can always do response.body.get(...) safely.
    if body_json is None and not body_text.strip():
        body_json = {}
    return RawHttpResponse(
        status_code=response.status_code,
        headers=headers,
        body_text=body_text,
        body_json=body_json,
    )
