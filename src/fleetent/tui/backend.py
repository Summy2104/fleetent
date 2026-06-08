"""Client-side gateway backend (websockets connection).

``GatewayBackend`` connects the TUI to the server's ``/ws`` endpoint: it sends
JSON-RPC requests and correlates responses by id, while a background receive loop
routes ``event`` notifications to ``on_event``. The websocket connection is
injectable (``connect_fn``) so the backend is unit-testable without a real socket.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fleetent.structured_logging import get_logger
from fleetent.tui import protocol as p

_logger = get_logger("tui.backend")

EventCallback = Callable[[dict[str, Any]], None]
ConnectFn = Callable[[], Awaitable[Any]]


class GatewayError(Exception):
    """A JSON-RPC error response was returned for a request."""

    def __init__(self, error: dict[str, Any]) -> None:
        super().__init__(str(error.get("message", error)))
        self.code = error.get("code")
        self.payload = error


class GatewayBackend:
    """Async client for the TUI WebSocket gateway."""

    def __init__(
        self,
        url: str,
        token: str,
        on_event: EventCallback,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.token = token
        self.on_event = on_event
        self.timeout = timeout
        # Optional async hook invoked when the receive loop ends (disconnect); the
        # app layer wires reconnect/backoff here.
        self.on_disconnect: Callable[[], Awaitable[None]] | None = None
        self._ws: Any | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None

    async def _default_connect(self) -> Any:
        import websockets

        return await websockets.connect(
            self.url, additional_headers={"Authorization": f"Bearer {self.token}"}
        )

    async def connect(self, connect_fn: ConnectFn | None = None) -> None:
        """Open the connection and start the background receive loop."""
        self._ws = await (connect_fn or self._default_connect)()
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("backend not connected")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        frame = p.encode_frame(
            {"jsonrpc": p.JSONRPC_VERSION, "id": request_id, "method": method, "params": params}
        )
        await self._ws.send(frame)
        try:
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self._pending.pop(request_id, None)

    async def send(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"message": message}
        if session_id is not None:
            params["session_id"] = session_id
        return await self._request(p.METHOD_SEND, params)

    async def abort(self, run_id: str) -> dict[str, Any]:
        return await self._request(p.METHOD_ABORT, {"run_id": run_id})

    async def approve(self, approval_id: str, decision: str) -> dict[str, Any]:
        return await self._request(
            p.METHOD_APPROVE, {"approval_id": approval_id, "decision": decision}
        )

    async def session_new(self) -> dict[str, Any]:
        return await self._request(p.METHOD_SESSION_NEW, {})

    async def session_list(self) -> dict[str, Any]:
        return await self._request(p.METHOD_SESSION_LIST, {})

    def _handle(self, raw: str) -> None:
        try:
            obj = p.decode_frame(raw)
        except p.ParseError:
            _logger.warn("backend_bad_frame", frame_preview=repr(raw[:200]))
            return
        if obj.get("method") == "event":
            self.on_event(obj.get("params", {}))
            return
        request_id = obj.get("id")
        future = self._pending.get(request_id) if request_id is not None else None
        if future is None or future.done():
            return
        if "error" in obj:
            future.set_exception(GatewayError(obj["error"]))
        else:
            future.set_result(obj.get("result", {}))

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                self._handle(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — connection dropped; surface via hook
            _logger.warn("backend_recv_ended", error=str(exc))
        if self.on_disconnect is not None:
            await self.on_disconnect()
