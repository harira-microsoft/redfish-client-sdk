"""
redfish_sdk/transport/http_client.py

Wraps httpx. Provides a uniform async request interface used by all layers
above. Never imported directly by callers.

Imports: models only.
"""

from __future__ import annotations

import json as _json

import httpx

from redfish_sdk.models.redfish_types import RawHttpResponse, TimeoutConfig, TLSConfig

_REDFISH_HEADERS = {
    "OData-Version": "4.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class HttpClient:
    """
    Single httpx.AsyncClient instance per SDK connection.
    Auth headers are NOT attached here — done by AuthManager.
    """

    def __init__(
        self,
        base_url: str,
        tls_config: TLSConfig,
        timeouts: TimeoutConfig,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=timeouts.connect_sec,
            read=timeouts.request_sec,
            write=timeouts.request_sec,
            pool=timeouts.request_sec,
        )
        self._verify = tls_config.verify
        # Async client — created lazily on first async request
        self._async_client: httpx.AsyncClient | None = None
        # Sync client — created lazily on first sync request
        self._sync_client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Async
    # ------------------------------------------------------------------

    async def request_async(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        client = await self._get_async_client()
        merged_headers = {**_REDFISH_HEADERS, **(headers or {})}
        content = _json.dumps(body).encode() if body is not None else None
        response = await client.request(
            method=method,
            url=path,
            headers=merged_headers,
            content=content,
        )
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

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> RawHttpResponse:
        client = self._get_sync_client()
        merged_headers = {**_REDFISH_HEADERS, **(headers or {})}
        content = _json.dumps(body).encode() if body is not None else None
        response = client.request(
            method=method,
            url=path,
            headers=merged_headers,
            content=content,
        )
        return _to_raw(response)

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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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
    return RawHttpResponse(
        status_code=response.status_code,
        headers=headers,
        body_text=body_text,
        body_json=body_json,
    )
