"""Client GatewayBackend: request frames, event dispatch, errors, reconnect (tui-gateway 6.1)."""

import asyncio
import json

import pytest

from fleetent.tui import protocol as p
from fleetent.tui.backend import GatewayBackend, GatewayError

_CLOSE = object()  # sentinel: end the incoming stream (simulates disconnect)


class FakeWS:
    """Duplex stand-in for a websockets client connection."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._incoming: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, text: str) -> None:
        self.sent.append(text)

    def push(self, frame: str) -> None:
        self._incoming.put_nowait(frame)

    def close_stream(self) -> None:
        self._incoming.put_nowait(_CLOSE)

    def __aiter__(self) -> "FakeWS":
        return self

    async def __anext__(self) -> str:
        item = await self._incoming.get()
        if item is _CLOSE:
            raise StopAsyncIteration
        return item

    async def close(self) -> None:
        self.closed = True


async def _backend_with_ws(on_event=None) -> tuple[GatewayBackend, FakeWS]:
    ws = FakeWS()
    backend = GatewayBackend("ws://x/ws", "ma-tok", on_event=on_event or (lambda e: None))

    async def connect_fn() -> FakeWS:
        return ws

    await backend.connect(connect_fn=connect_fn)
    return backend, ws


async def _request_and_respond(backend, ws, coro_factory, result):
    """Run a backend request, capture its frame, feed a matching response, return result."""
    task = asyncio.create_task(coro_factory())
    await asyncio.sleep(0)  # let the request frame get written
    sent = json.loads(ws.sent[-1])
    ws.push(p.encode_frame(p.make_response(sent["id"], result)))
    return sent, await task


async def test_send_emits_send_frame_and_returns_result():
    backend, ws = await _backend_with_ws()
    sent, res = await _request_and_respond(
        backend, ws, lambda: backend.send("hi", session_id="s1"), {"run_id": "r1"}
    )
    assert sent["jsonrpc"] == "2.0" and sent["method"] == "send"
    assert sent["params"] == {"message": "hi", "session_id": "s1"}
    assert res == {"run_id": "r1"}


async def test_abort_approve_session_frames():
    backend, ws = await _backend_with_ws()
    sent, _ = await _request_and_respond(backend, ws, lambda: backend.abort("r1"), {"ok": True})
    assert sent["method"] == "abort" and sent["params"] == {"run_id": "r1"}

    sent, _ = await _request_and_respond(
        backend, ws, lambda: backend.approve("a1", "approved"), {"ok": True}
    )
    assert sent["method"] == "approve"
    assert sent["params"] == {"approval_id": "a1", "decision": "approved"}

    sent, _ = await _request_and_respond(
        backend, ws, lambda: backend.session_list(), {"sessions": []}
    )
    assert sent["method"] == "session.list"


async def test_on_event_callback_receives_parsed_event():
    received = []
    backend, ws = await _backend_with_ws(on_event=received.append)
    ws.push(p.encode_frame(p.make_event(p.EVENT_TEXT_DELTA, {"content": "hi"}, run_id="r1")))
    await asyncio.sleep(0.01)
    assert received == [{"type": "text_delta", "payload": {"content": "hi"}, "run_id": "r1"}]


async def test_request_error_response_raises_gateway_error():
    backend, ws = await _backend_with_ws()
    task = asyncio.create_task(backend.session_new())
    await asyncio.sleep(0)
    rid = json.loads(ws.sent[-1])["id"]
    ws.push(p.encode_frame(p.make_error(rid, p.METHOD_NOT_FOUND, "nope")))
    with pytest.raises(GatewayError):
        await task


async def test_request_times_out():
    ws = FakeWS()
    backend = GatewayBackend("ws://x/ws", "tok", on_event=lambda e: None, timeout=0.05)

    async def connect_fn() -> FakeWS:
        return ws

    await backend.connect(connect_fn=connect_fn)
    with pytest.raises(asyncio.TimeoutError):
        await backend.send("hi")  # no response pushed → times out


async def test_disconnect_invokes_reconnect_hook():
    ws = FakeWS()
    fired = asyncio.Event()
    backend = GatewayBackend("ws://x/ws", "tok", on_event=lambda e: None)

    async def _hook() -> None:
        fired.set()

    backend.on_disconnect = _hook

    async def connect_fn() -> FakeWS:
        return ws

    await backend.connect(connect_fn=connect_fn)
    ws.close_stream()  # simulate the server dropping the connection
    await asyncio.wait_for(fired.wait(), 0.2)
