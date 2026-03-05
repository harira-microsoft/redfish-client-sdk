"""
redfish_sdk/protocol/task.py

RedfishTask — the handle for 202 Accepted responses.
TaskManager — internal polling logic.
Imports: transport, models, protocol/response.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Callable, Awaitable

from pydantic import BaseModel, Field

from redfish_sdk.protocol.response import RedfishMessage, RedfishResponse, build_response

if TYPE_CHECKING:
    from redfish_sdk.transport.http_client import HttpClient
    from redfish_sdk.models.redfish_types import AuthState, TimeoutConfig


class TaskState(str, Enum):
    NEW = "New"
    STARTING = "Starting"
    RUNNING = "Running"
    SUSPENDED = "Suspended"
    INTERRUPTED = "Interrupted"
    PENDING = "Pending"
    STOPPING = "Stopping"
    COMPLETED = "Completed"
    KILLED = "Killed"
    EXCEPTION = "Exception"
    SERVICE = "Service"
    CANCELLING = "Cancelling"
    CANCELLED = "Cancelled"


_TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.KILLED,
    TaskState.EXCEPTION,
    TaskState.CANCELLED,
}

_FAILED_STATES = {TaskState.KILLED, TaskState.EXCEPTION}


class RedfishTask(BaseModel):
    task_uri: str
    task_id: str = ""
    state: TaskState = TaskState.NEW
    percent_complete: int | None = None
    messages: list[RedfishMessage] = Field(default_factory=list)

    # Private transport refs — not serialized
    _http: object = None        # HttpClient
    _auth_state: object = None  # AuthState
    _timeouts: object = None    # TimeoutConfig

    model_config = {"arbitrary_types_allowed": True}

    def _bind(
        self,
        http: HttpClient,
        auth_state: AuthState,
        timeouts: TimeoutConfig,
    ) -> None:
        """Called by the SDK after construction to wire transport."""
        self._http = http
        self._auth_state = auth_state
        self._timeouts = timeouts

    # ------------------------------------------------------------------
    # Wait
    # ------------------------------------------------------------------

    async def wait_async(
        self,
        poll_interval_sec: float | None = None,
        timeout_sec: float | None = None,
    ) -> RedfishResponse:
        manager = TaskManager(self, self._http, self._auth_state, self._timeouts)  # type: ignore[arg-type]
        return await manager.poll_async(poll_interval_sec, timeout_sec)

    def wait(
        self,
        poll_interval_sec: float | None = None,
        timeout_sec: float | None = None,
    ) -> RedfishResponse:
        return asyncio.run(self.wait_async(poll_interval_sec, timeout_sec))

    # ------------------------------------------------------------------
    # Monitor
    # ------------------------------------------------------------------

    async def monitor_async(
        self,
        on_state_change: Callable[[TaskState, RedfishTask], None]
        | Callable[[TaskState, RedfishTask], Awaitable[None]],
        timeout_sec: float | None = None,
    ) -> None:
        manager = TaskManager(self, self._http, self._auth_state, self._timeouts)  # type: ignore[arg-type]
        await manager.monitor_async(on_state_change, timeout_sec)

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel_async(self) -> RedfishResponse:
        from redfish_sdk.transport.auth import AuthManager
        headers = AuthManager.attach_auth(self._auth_state, {})  # type: ignore[arg-type]
        raw = await self._http.request_async("DELETE", self.task_uri, headers=headers)  # type: ignore[union-attr]
        return build_response(raw.status_code, raw.headers, raw.body_json, raw.body_text)

    def cancel(self) -> RedfishResponse:
        return asyncio.run(self.cancel_async())


class TaskManager:
    """Internal. Drives task polling. Not part of the public API."""

    def __init__(
        self,
        task: RedfishTask,
        http: HttpClient,
        auth_state: AuthState,
        timeouts: TimeoutConfig,
    ) -> None:
        self._task = task
        self._http = http
        self._auth_state = auth_state
        self._timeouts = timeouts

    async def poll_async(
        self,
        poll_interval_sec: float | None,
        timeout_sec: float | None,
    ) -> RedfishResponse:
        from redfish_sdk.errors import RedfishTaskFailedError, RedfishTaskTimeoutError
        from redfish_sdk.transport.auth import AuthManager

        interval = poll_interval_sec or self._timeouts.task_poll_sec
        limit = timeout_sec or self._timeouts.task_timeout_sec
        elapsed = 0.0
        last_response: RedfishResponse | None = None

        while elapsed < limit:
            headers = AuthManager.attach_auth(self._auth_state, {})
            raw = await self._http.request_async("GET", self._task.task_uri, headers=headers)
            last_response = build_response(
                raw.status_code, raw.headers, raw.body_json, raw.body_text
            )
            self._update_task(raw.body_json)

            if self._task.state in _TERMINAL_STATES:
                if self._task.state in _FAILED_STATES:
                    raise RedfishTaskFailedError(
                        f"Task {self._task.task_id} reached state {self._task.state}",
                        task=self._task,
                    )
                return last_response

            await asyncio.sleep(interval)
            elapsed += interval

        raise RedfishTaskTimeoutError(
            f"Task {self._task.task_id} did not complete within {limit}s",
            task=self._task,
        )

    async def monitor_async(
        self,
        on_state_change: Callable,
        timeout_sec: float | None,
    ) -> None:
        from redfish_sdk.transport.auth import AuthManager

        interval = self._timeouts.task_poll_sec
        limit = timeout_sec or self._timeouts.task_timeout_sec
        elapsed = 0.0
        previous_state: TaskState | None = None

        while elapsed < limit:
            headers = AuthManager.attach_auth(self._auth_state, {})
            raw = await self._http.request_async("GET", self._task.task_uri, headers=headers)
            self._update_task(raw.body_json)

            if self._task.state != previous_state:
                previous_state = self._task.state
                result = on_state_change(self._task.state, self._task)
                if asyncio.iscoroutine(result):
                    await result

            if self._task.state in _TERMINAL_STATES:
                return

            await asyncio.sleep(interval)
            elapsed += interval

    def _update_task(self, body: dict | list | None) -> None:
        if not isinstance(body, dict):
            return
        raw_state = body.get("TaskState")
        if raw_state:
            try:
                self._task.state = TaskState(raw_state)
            except ValueError:
                pass
        pct = body.get("PercentComplete")
        if pct is not None:
            self._task.percent_complete = int(pct)
        msgs = body.get("Messages", [])
        self._task.messages = [
            RedfishMessage.model_validate(m) for m in msgs if isinstance(m, dict)
        ]
