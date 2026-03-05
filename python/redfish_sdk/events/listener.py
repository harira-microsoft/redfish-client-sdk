"""
Redfish Event Listener — embedded HTTP/HTTPS server for receiving
push-mode event notifications from a BMC EventService subscription.

Design ref: RSDK-DESIGN-001 §15

Usage pattern:
    listener = RedfishEventListener(port=9090)
    listener.use_context(ctx)

    @listener.on_event
    async def handle(event: RedfishEvent) -> None:
        print(event.event_type, event.message_id)

    listener.start()
    # ... later
    listener.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from aiohttp import web

from redfish_sdk.services.event_service import RedfishEvent

if TYPE_CHECKING:
    from redfish_sdk.context import ClientContext

_LOG = logging.getLogger(__name__)

# Type alias for callbacks — sync or async
_SyncCallback = Callable[[RedfishEvent], None]
_AsyncCallback = Callable[[RedfishEvent], Coroutine[Any, Any, None]]
_AnyCallback = _SyncCallback | _AsyncCallback


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_async_callable(obj: Any) -> bool:
    """Return True if *obj* is a coroutine function."""
    return asyncio.iscoroutinefunction(obj)


async def _dispatch(callback: _AnyCallback, event: RedfishEvent) -> None:
    """Call *callback* with *event*, awaiting if it is async."""
    try:
        if _is_async_callable(callback):
            await callback(event)  # type: ignore[arg-type]
        else:
            callback(event)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        _LOG.exception("Event callback raised an unhandled exception")


# ---------------------------------------------------------------------------
# RedfishEventListener
# ---------------------------------------------------------------------------

class RedfishEventListener:
    """Embedded HTTP/HTTPS server that receives Redfish push-mode events.

    The BMC POSTs JSON payloads to this server whenever a subscribed event
    fires.  The listener parses each payload, constructs :class:`RedfishEvent`
    objects, and dispatches them to registered callbacks.

    Parameters
    ----------
    port:
        TCP port on which the server will listen.
    host:
        Interface to bind (default ``"0.0.0.0"`` — all interfaces).
    tls_cert:
        Path to a PEM certificate file.  When both *tls_cert* and *tls_key*
        are supplied the server runs HTTPS; otherwise plain HTTP.
    tls_key:
        Path to the corresponding PEM private key file.
    path:
        URL path to register the event handler on (default ``"/events"``).
    """

    def __init__(
        self,
        port: int,
        host: str = "0.0.0.0",
        tls_cert: str | None = None,
        tls_key: str | None = None,
        path: str = "/events",
    ) -> None:
        self._port = port
        self._host = host
        self._tls_cert = tls_cert
        self._tls_key = tls_key
        self._path = path if path.startswith("/") else f"/{path}"

        self._ctx: ClientContext | None = None

        # Callback registries
        self._global_callbacks: list[_AnyCallback] = []
        self._type_callbacks: dict[str, list[_AnyCallback]] = {}
        self._registry_callbacks: dict[str, list[_AnyCallback]] = {}

        # Runtime state
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def use_context(self, ctx: "ClientContext") -> None:
        """Attach a :class:`~redfish_sdk.context.ClientContext`.

        When attached, registry resolution is attempted for each incoming
        event's ``MessageId`` field.  The context is not required for the
        listener to operate.
        """
        self._ctx = ctx

    # ------------------------------------------------------------------
    # Decorator / registration API
    # ------------------------------------------------------------------

    def on_event(self, callback: _AnyCallback) -> _AnyCallback:
        """Register *callback* for **every** incoming event.

        Can be used as a plain call or as a decorator::

            listener.on_event(my_callback)

            @listener.on_event
            async def my_callback(event: RedfishEvent) -> None: ...
        """
        self._global_callbacks.append(callback)
        return callback

    def on_event_type(self, event_type: str, callback: _AnyCallback) -> None:
        """Register *callback* for events whose ``event_type`` matches.

        Parameters
        ----------
        event_type:
            The Redfish ``EventType`` string, e.g. ``"Alert"``,
            ``"ResourceUpdated"``, ``"StatusChange"``.
        callback:
            Sync or async callable accepting a single
            :class:`~redfish_sdk.services.event_service.RedfishEvent`.
        """
        self._type_callbacks.setdefault(event_type, []).append(callback)

    def on_registry(self, registry_prefix: str, callback: _AnyCallback) -> None:
        """Register *callback* for events whose ``MessageId`` starts with *registry_prefix*.

        Parameters
        ----------
        registry_prefix:
            Registry prefix, e.g. ``"Base"``, ``"iLO"``, ``"OpenBMC"``.
        callback:
            Sync or async callable accepting a single
            :class:`~redfish_sdk.services.event_service.RedfishEvent`.
        """
        self._registry_callbacks.setdefault(registry_prefix, []).append(callback)

    # ------------------------------------------------------------------
    # Lifecycle — sync wrappers (run server in background thread)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the listener in a background thread (non-blocking).

        The embedded aiohttp server runs on a dedicated event loop so it
        does not interfere with any caller-side event loop.

        Raises
        ------
        RuntimeError
            If the listener is already running.
        """
        if self._running:
            raise RuntimeError("RedfishEventListener is already running")

        ready_event = threading.Event()
        error_holder: list[BaseException] = []

        def _thread_target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self._start_server(ready_event, error_holder))
                loop.run_forever()
            finally:
                loop.run_until_complete(self._stop_server())
                loop.close()

        self._thread = threading.Thread(
            target=_thread_target,
            daemon=True,
            name="redfish-event-listener",
        )
        self._thread.start()
        ready_event.wait(timeout=10.0)

        if error_holder:
            raise error_holder[0]

        _LOG.info("RedfishEventListener started on %s", self.listen_url)

    def stop(self) -> None:
        """Stop the background listener thread.

        Blocks until the server has fully shut down (up to 5 seconds).
        """
        if not self._running or self._loop is None:
            return

        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)

        self._running = False
        _LOG.info("RedfishEventListener stopped")

    # ------------------------------------------------------------------
    # Lifecycle — async API (use when inside an existing event loop)
    # ------------------------------------------------------------------

    async def start_async(self) -> None:
        """Start the listener on the **current** event loop (awaitable).

        Use this variant when you are already inside an async context and
        want to integrate the listener into your own event loop rather than
        spawning a background thread.

        Raises
        ------
        RuntimeError
            If the listener is already running.
        """
        if self._running:
            raise RuntimeError("RedfishEventListener is already running")

        self._loop = asyncio.get_running_loop()
        ready_event = threading.Event()
        error_holder: list[BaseException] = []
        await self._start_server(ready_event, error_holder)
        if error_holder:
            raise error_holder[0]
        _LOG.info("RedfishEventListener (async) started on %s", self.listen_url)

    async def stop_async(self) -> None:
        """Stop the listener (awaitable)."""
        if not self._running:
            return
        await self._stop_server()
        self._running = False
        _LOG.info("RedfishEventListener (async) stopped")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True if the embedded server is currently accepting connections."""
        return self._running

    @property
    def listen_url(self) -> str:
        """The URL at which the BMC should POST events.

        Example: ``http://192.168.1.10:9090/events``
        """
        scheme = "https" if (self._tls_cert and self._tls_key) else "http"
        return f"{scheme}://{self._host}:{self._port}{self._path}"

    # ------------------------------------------------------------------
    # Internal server management
    # ------------------------------------------------------------------

    async def _start_server(
        self,
        ready_event: threading.Event,
        error_holder: list[BaseException],
    ) -> None:
        """Build and start the aiohttp application."""
        app = web.Application()
        app.router.add_post(self._path, self._handle_post)
        app.router.add_get(self._path, self._handle_health)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()

        ssl_ctx: ssl.SSLContext | None = None
        if self._tls_cert and self._tls_key:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            try:
                ssl_ctx.load_cert_chain(certfile=self._tls_cert, keyfile=self._tls_key)
            except Exception as exc:  # noqa: BLE001
                error_holder.append(exc)
                ready_event.set()
                return

        self._site = web.TCPSite(
            self._runner,
            host=self._host,
            port=self._port,
            ssl_context=ssl_ctx,
        )

        try:
            await self._site.start()
            self._running = True
        except Exception as exc:  # noqa: BLE001
            error_holder.append(exc)
        finally:
            ready_event.set()

    async def _stop_server(self) -> None:
        """Tear down the aiohttp runner."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    # ------------------------------------------------------------------
    # Request handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, request: web.Request) -> web.Response:  # noqa: ARG002
        """Simple GET handler — useful for connectivity probes."""
        return web.Response(status=200, text="Redfish Event Listener OK")

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle an incoming event POST from the BMC.

        The BMC posts a JSON body conforming to the Redfish ``EventMessage``
        schema.  We parse every record in ``Events[]`` and dispatch callbacks.

        Always responds ``204 No Content`` to acknowledge delivery, even on
        parse errors (to avoid the BMC retrying malformed payloads).
        """
        try:
            body = await request.read()
            payload = json.loads(body)
        except Exception:  # noqa: BLE001
            _LOG.warning("Event listener received unparseable payload; ignoring")
            return web.Response(status=204)

        events = self._parse_payload(payload)

        dispatch_tasks = []
        for event in events:
            dispatch_tasks.extend(self._build_dispatch_tasks(event))

        if dispatch_tasks:
            await asyncio.gather(*dispatch_tasks, return_exceptions=True)

        return web.Response(status=204)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_payload(self, payload: dict[str, Any]) -> list[RedfishEvent]:
        """Extract :class:`RedfishEvent` objects from a raw BMC POST body."""
        records = payload.get("Events", [payload])
        events: list[RedfishEvent] = []

        for record in records:
            if not isinstance(record, dict):
                continue

            # Primary identification fields
            event_type = record.get("EventType", "")
            message_id = record.get("MessageId", "")
            message = record.get("Message", "")
            severity = record.get("Severity", record.get("MessageSeverity", ""))
            origin_of_condition = record.get("OriginOfCondition", {})

            if isinstance(origin_of_condition, dict):
                origin_uri = origin_of_condition.get("@odata.id", "")
            else:
                origin_uri = str(origin_of_condition)

            # Build the event
            evt = RedfishEvent(
                event_type=event_type,
                message_id=message_id,
                message=message,
                severity=severity,
                origin_of_condition=origin_uri,
                raw=record,
            )
            events.append(evt)

        return events

    def _build_dispatch_tasks(self, event: RedfishEvent) -> list[Coroutine[Any, Any, None]]:
        """Return a list of coroutines that will dispatch *event* to callbacks."""
        tasks: list[Coroutine[Any, Any, None]] = []

        # 1. Global callbacks
        for cb in self._global_callbacks:
            tasks.append(_dispatch(cb, event))

        # 2. EventType-filtered callbacks
        if event.event_type:
            for cb in self._type_callbacks.get(event.event_type, []):
                tasks.append(_dispatch(cb, event))

        # 3. Registry-prefix callbacks — match on MessageId prefix before '.'
        if event.message_id:
            prefix = event.message_id.split(".")[0]
            for cb in self._registry_callbacks.get(prefix, []):
                tasks.append(_dispatch(cb, event))

        return tasks
