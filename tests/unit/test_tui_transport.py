"""WSTransport: peer-gone vs real-error classification, idempotent close (tui-gateway 3.1)."""

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from fleetent.tui import protocol as p
from fleetent.tui.transport import WSTransport


class FakeWS:
    """Minimal stand-in for a starlette WebSocket; send_text/close may be told to raise."""

    def __init__(self, send_exc: BaseException | None = None) -> None:
        self.sent: list[str] = []
        self.closed = 0
        self._send_exc = send_exc

    async def send_text(self, text: str) -> None:
        if self._send_exc is not None:
            raise self._send_exc
        self.sent.append(text)

    async def close(self, code: int = 1000) -> None:
        self.closed += 1


async def test_write_success_returns_true_and_sends_frame():
    ws = FakeWS()
    t = WSTransport(ws)
    ok = await t.write(p.make_event(p.EVENT_TEXT_DELTA, {"content": "hi"}))
    assert ok is True
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0])["params"]["payload"] == {"content": "hi"}
    assert ws.sent[0].endswith("\n")


async def test_write_peer_gone_websocketdisconnect_returns_false():
    t = WSTransport(FakeWS(send_exc=WebSocketDisconnect(code=1006)))
    assert await t.write({"a": 1}) is False


async def test_write_peer_gone_closed_runtimeerror_returns_false():
    t = WSTransport(FakeWS(send_exc=RuntimeError('Cannot call "send" once a close ...')))
    assert await t.write({"a": 1}) is False


async def test_write_real_error_is_reraised_not_disguised():
    t = WSTransport(FakeWS(send_exc=ValueError("boom serialize")))
    with pytest.raises(ValueError, match="boom"):
        await t.write({"a": 1})


async def test_write_after_peer_gone_short_circuits_false():
    ws = FakeWS(send_exc=WebSocketDisconnect(code=1006))
    t = WSTransport(ws)
    assert await t.write({"a": 1}) is False
    # transport now marked dead → subsequent writes return False without touching ws
    assert await t.write({"b": 2}) is False


async def test_close_is_idempotent():
    ws = FakeWS()
    t = WSTransport(ws)
    await t.close()
    await t.close()
    assert ws.closed == 1  # second close is a no-op
