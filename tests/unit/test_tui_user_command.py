"""TUI: /user command (parse + dispatch METHOD_USER) and agent_name injection wiring."""

from __future__ import annotations

import asyncio
from typing import Any

from fleetent.runtime import user_instructions as ui
from fleetent.tui import dispatch as d
from fleetent.tui import protocol as p
from fleetent.tui.commands import KNOWN_COMMANDS, parse_command


class FakeTransport:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    async def write(self, obj: dict[str, Any]) -> bool:
        self.written.append(obj)
        return True

    async def close(self) -> None:
        pass


async def _drain(conn: d.Connection) -> None:
    tasks = list(conn._tasks)
    if tasks:
        await asyncio.gather(*tasks)


def test_user_is_known_command_and_parses() -> None:
    assert "user" in KNOWN_COMMANDS
    cmd = parse_command("/user clear")
    assert cmd is not None
    assert cmd.name == "user"
    assert cmd.args == ["clear"]


async def test_dispatch_user_appends_and_returns_receipt() -> None:
    conn = d.Connection(user_id="u1", transport=FakeTransport(), agent_name="default")
    resp = await d.dispatch(
        conn,
        {"id": 1, "method": p.METHOD_USER, "params": {"text": "/user 用中文回答"}},
    )
    assert "已追加" in resp["result"]["reply"]
    assert "用中文回答" in ui.load("default")


async def test_dispatch_user_view_empty() -> None:
    conn = d.Connection(user_id="u1", transport=FakeTransport(), agent_name="default")
    resp = await d.dispatch(conn, {"id": 2, "method": p.METHOD_USER, "params": {"text": "/user"}})
    assert "尚未设置" in resp["result"]["reply"]


async def test_dispatch_send_passes_agent_name(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_stream(message, **kwargs):
        captured.update(kwargs)
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(d, "run_stream", fake_run_stream)
    conn = d.Connection(user_id="u1", transport=FakeTransport(), agent_name="default")
    await d.dispatch(conn, {"id": 3, "method": "send", "params": {"message": "hi"}})
    await _drain(conn)
    assert captured.get("agent_name") == "default"
