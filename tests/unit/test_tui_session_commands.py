"""TUI: generalized command method (METHOD_COMMAND) routing through the dispatcher."""

from __future__ import annotations

from typing import Any

from fleetent.tui import dispatch as d
from fleetent.tui import protocol as p
from fleetent.tui.commands import KNOWN_COMMANDS


class FakeTransport:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    async def write(self, obj: dict[str, Any]) -> bool:
        self.written.append(obj)
        return True

    async def close(self) -> None:
        pass


def test_session_command_names_known() -> None:
    for name in ("clear", "compact", "context", "usage", "cost"):
        assert name in KNOWN_COMMANDS


async def test_dispatch_command_clear(monkeypatch) -> None:
    from fleetent.session import manager as session_mgr

    cleared: list[str] = []

    async def fake_clear(sid):
        cleared.append(sid)

    monkeypatch.setattr(session_mgr, "clear", fake_clear)
    conn = d.Connection(user_id="u1", transport=FakeTransport(), agent_name="default")
    resp = await d.dispatch(
        conn, {"id": 1, "method": p.METHOD_COMMAND, "params": {"text": "/clear"}}
    )
    assert cleared == [conn.session_id]
    assert "清空" in resp["result"]["reply"]


async def test_dispatch_command_non_command_passthrough() -> None:
    # A non-command returns a reply prompting normal send (handle_command -> None).
    conn = d.Connection(user_id="u1", transport=FakeTransport(), agent_name="default")
    resp = await d.dispatch(
        conn, {"id": 2, "method": p.METHOD_COMMAND, "params": {"text": "hello"}}
    )
    # reply is None-ish / hint; key is it does not raise and returns a result object
    assert "result" in resp
