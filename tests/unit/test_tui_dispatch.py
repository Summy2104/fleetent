"""TUI gateway dispatch: send streaming + session.* + unknown method (tui-gateway 4.1)."""

import asyncio
from typing import Any

from fleetent.tui import dispatch as d
from fleetent.tui import protocol as p


class FakeTransport:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    async def write(self, obj: dict[str, Any]) -> bool:
        self.written.append(obj)
        return True

    async def close(self) -> None:
        pass


def _conn(transport: FakeTransport) -> d.Connection:
    return d.Connection(user_id="u1", transport=transport)


async def _drain(conn: d.Connection) -> None:
    tasks = list(conn._tasks)
    if tasks:
        await asyncio.gather(*tasks)


async def test_send_returns_run_id(monkeypatch):
    async def fake_run_stream(message, **kwargs):
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(d, "run_stream", fake_run_stream)
    t = FakeTransport()
    conn = _conn(t)
    resp = await d.dispatch(
        conn, {"jsonrpc": "2.0", "id": 1, "method": "send", "params": {"message": "hi"}}
    )
    assert resp["id"] == 1
    assert isinstance(resp["result"]["run_id"], str) and resp["result"]["run_id"]
    await _drain(conn)


async def test_send_maps_run_stream_events_in_order(monkeypatch):
    async def fake_run_stream(message, **kwargs):
        yield {"type": "tool_call", "name": "calc", "args": {"x": 1}}
        yield {"type": "tool_result", "name": "calc", "content": "2"}
        yield {"type": "text_delta", "content": "the answer"}
        yield {"type": "done", "content": "the answer"}

    monkeypatch.setattr(d, "run_stream", fake_run_stream)
    t = FakeTransport()
    conn = _conn(t)
    resp = await d.dispatch(conn, {"id": 2, "method": "send", "params": {"message": "hi"}})
    run_id = resp["result"]["run_id"]
    await _drain(conn)

    events = [w for w in t.written if w.get("method") == "event"]
    assert [e["params"]["type"] for e in events] == [
        "tool_call",
        "tool_result",
        "text_delta",
        "done",
    ]
    assert all(e["params"]["run_id"] == run_id for e in events)
    # payload preserves the non-type fields
    assert events[0]["params"]["payload"] == {"name": "calc", "args": {"x": 1}}
    assert events[2]["params"]["payload"] == {"content": "the answer"}


async def test_send_uses_message_and_clears_token_when_done(monkeypatch):
    async def fake_run_stream(message, **kwargs):
        assert message == "compute"
        yield {"type": "done", "content": "x"}

    monkeypatch.setattr(d, "run_stream", fake_run_stream)
    conn = _conn(FakeTransport())
    resp = await d.dispatch(conn, {"id": 3, "method": "send", "params": {"message": "compute"}})
    await _drain(conn)
    assert resp["result"]["run_id"] not in conn.cancel_tokens  # token removed after completion


async def test_session_new_returns_user_scoped_id():
    conn = _conn(FakeTransport())
    resp = await d.dispatch(conn, {"id": 4, "method": "session.new", "params": {}})
    sid = resp["result"]["session_id"]
    assert sid.startswith("tui:u1:")
    assert conn.session_id == sid  # new session becomes the bound session


async def test_session_list_only_this_user(monkeypatch):
    captured = {}

    def fake_list(prefix=""):
        captured["prefix"] = prefix
        return ["tui:u1:aaa", "tui:u1:bbb"]

    monkeypatch.setattr(d.session_mgr, "list_session_ids", fake_list)
    conn = _conn(FakeTransport())
    resp = await d.dispatch(conn, {"id": 5, "method": "session.list", "params": {}})
    assert resp["result"]["sessions"] == ["tui:u1:aaa", "tui:u1:bbb"]
    assert captured["prefix"] == "tui:u1:"  # scoped to this connection's user


async def test_unknown_method_returns_method_not_found():
    conn = _conn(FakeTransport())
    resp = await d.dispatch(conn, {"id": 6, "method": "frobnicate", "params": {}})
    assert resp["error"]["code"] == p.METHOD_NOT_FOUND
