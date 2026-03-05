"""
redfish_sdk/transport/auth.py

Executes auth flows at connect time and manages per-request auth attachment.
Imports: http_client, models.
"""

from __future__ import annotations

from redfish_sdk.models.redfish_types import AuthMode, AuthState, Credentials
from redfish_sdk.transport.http_client import HttpClient


class AuthManager:

    def __init__(
        self,
        http_client: HttpClient,
        credentials: Credentials,
        auth_mode: AuthMode,
    ) -> None:
        self._http = http_client
        self._credentials = credentials
        self._mode = auth_mode

    # ------------------------------------------------------------------
    # Authenticate — called once at connect time
    # ------------------------------------------------------------------

    async def authenticate_async(self) -> AuthState:
        if self._mode == AuthMode.SESSION:
            return await self._session_auth_async()
        return await self._stateless_auth_async()

    def authenticate(self) -> AuthState:
        if self._mode == AuthMode.SESSION:
            return self._session_auth()
        return self._stateless_auth()

    # ------------------------------------------------------------------
    # Auth attachment — called on every outbound request
    # ------------------------------------------------------------------

    @staticmethod
    def attach_auth(state: AuthState, headers: dict[str, str]) -> dict[str, str]:
        out = dict(headers)
        if state.mode == AuthMode.SESSION and state.session_token:
            out["X-Auth-Token"] = state.session_token
        elif state.mode == AuthMode.STATELESS and state.credentials:
            out["Authorization"] = state.credentials.as_basic_header()
        return out

    # ------------------------------------------------------------------
    # Logout — session mode only
    # ------------------------------------------------------------------

    async def logout_async(self, state: AuthState) -> None:
        if state.mode == AuthMode.SESSION and state.session_uri:
            try:
                headers = self.attach_auth(state, {})
                await self._http.request_async("DELETE", state.session_uri, headers=headers)
            except Exception:
                pass  # best-effort on logout

    def logout(self, state: AuthState) -> None:
        if state.mode == AuthMode.SESSION and state.session_uri:
            try:
                headers = self.attach_auth(state, {})
                self._http.request("DELETE", state.session_uri, headers=headers)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal flows
    # ------------------------------------------------------------------

    async def _session_auth_async(self) -> AuthState:
        response = await self._http.request_async(
            method="POST",
            path="/redfish/v1/SessionService/Sessions",
            body={
                "UserName": self._credentials.username,
                "Password": self._credentials.password,
            },
        )
        return self._extract_session_state(response.status_code, response.headers)

    def _session_auth(self) -> AuthState:
        response = self._http.request(
            method="POST",
            path="/redfish/v1/SessionService/Sessions",
            body={
                "UserName": self._credentials.username,
                "Password": self._credentials.password,
            },
        )
        return self._extract_session_state(response.status_code, response.headers)

    def _extract_session_state(
        self, status_code: int, headers: dict[str, str]
    ) -> AuthState:
        from redfish_sdk.errors import RedfishAuthError
        if status_code not in (200, 201):
            raise RedfishAuthError(
                f"Session creation failed — HTTP {status_code}"
            )
        token = headers.get("x-auth-token") or headers.get("X-Auth-Token")
        location = headers.get("location") or headers.get("Location")
        if not token:
            raise RedfishAuthError("Session created but no X-Auth-Token in response")
        return AuthState(
            mode=AuthMode.SESSION,
            session_token=token,
            session_uri=location,
            credentials=self._credentials,
        )

    async def _stateless_auth_async(self) -> AuthState:
        auth_headers = {"Authorization": self._credentials.as_basic_header()}
        response = await self._http.request_async(
            method="GET", path="/redfish/v1", headers=auth_headers
        )
        self._check_stateless(response.status_code)
        return AuthState(
            mode=AuthMode.STATELESS,
            credentials=self._credentials,
        )

    def _stateless_auth(self) -> AuthState:
        auth_headers = {"Authorization": self._credentials.as_basic_header()}
        response = self._http.request(
            method="GET", path="/redfish/v1", headers=auth_headers
        )
        self._check_stateless(response.status_code)
        return AuthState(
            mode=AuthMode.STATELESS,
            credentials=self._credentials,
        )

    @staticmethod
    def _check_stateless(status_code: int) -> None:
        from redfish_sdk.errors import RedfishAuthError
        if status_code in (401, 403):
            raise RedfishAuthError(
                f"Stateless auth rejected — HTTP {status_code}"
            )
