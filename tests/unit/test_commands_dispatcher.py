"""Unit: shared command dispatcher core + /user integration.

Pure dispatch logic; /user exercises real file I/O under the pinned FLEETENT_HOME.
"""

from __future__ import annotations

import contextlib

from fleetent.runtime import commands
from fleetent.runtime import user_instructions as ui


@contextlib.asynccontextmanager
async def _fake_lock(sid):
    yield


def _wire_session(monkeypatch, msgs):
    """Mock session_mgr lock/load/save; return a list capturing saved messages."""
    from fleetent.session import manager as session_mgr

    saved: list = []
    monkeypatch.setattr(session_mgr, "session_lock", _fake_lock)

    async def fake_load(_sid):
        return list(msgs)

    async def fake_save(_sid, m, *a, **k):
        saved.append(m)

    monkeypatch.setattr(session_mgr, "load", fake_load)
    monkeypatch.setattr(session_mgr, "save", fake_save)
    return saved


def _ctx(agent_name="default", session_id="s1", user_id="u1") -> commands.CommandContext:
    return commands.CommandContext(agent_name=agent_name, session_id=session_id, user_id=user_id)


async def test_non_command_returns_none() -> None:
    assert await commands.handle_command(_ctx(), "你好") is None
    assert await commands.handle_command(_ctx(), "  hi  ") is None


async def test_unknown_slash_returns_none() -> None:
    # Unknown slash word is treated as normal text (sent to the model), not swallowed.
    assert await commands.handle_command(_ctx(), "/frobnicate x") is None


async def test_user_command_via_dispatcher() -> None:
    reply = await commands.handle_command(_ctx(), "/user 永远用中文回答")
    assert reply is not None and "已追加" in reply
    assert "永远用中文回答" in ui.load("default")


async def test_user_command_works_without_session() -> None:
    # /user is agent-scoped: usable even when there is no session (e.g. CLI one-shot).
    reply = await commands.handle_command(_ctx(session_id=None), "/user")
    assert reply is not None and "尚未设置" in reply


# --- /clear + session guard -------------------------------------------------


async def test_session_command_without_session_returns_hint() -> None:
    reply = await commands.handle_command(_ctx(session_id=None), "/clear")
    assert reply is not None and "不可用" in reply


async def test_clear_calls_manager_and_receipts(monkeypatch) -> None:
    from fleetent.session import manager as session_mgr

    called: list[str] = []

    async def fake_clear(sid):
        called.append(sid)

    monkeypatch.setattr(session_mgr, "clear", fake_clear)
    reply = await commands.handle_command(_ctx(session_id="s1"), "/clear")
    assert called == ["s1"]
    assert reply is not None and "清空" in reply


# --- /compact ---------------------------------------------------------------


async def test_compact_compresses_and_saves(monkeypatch) -> None:
    from fleetent.runtime import context

    msgs = [{"role": "user", "content": "hello world"} for _ in range(10)]
    saved = _wire_session(monkeypatch, msgs)
    monkeypatch.setattr(context, "maybe_compress", lambda m, **k: m[:3])

    reply = await commands.handle_command(_ctx(session_id="s1"), "/compact")

    assert saved and len(saved[0]) == 3  # compressed result was persisted
    assert reply is not None
    assert "10" in reply and "3" in reply  # before→after message counts


# --- /context ---------------------------------------------------------------


async def test_context_reports_count_and_tokens(monkeypatch) -> None:
    msgs = [{"role": "user", "content": "hello"} for _ in range(5)]
    _wire_session(monkeypatch, msgs)

    reply = await commands.handle_command(_ctx(session_id="s1"), "/context")

    assert reply is not None
    assert "5" in reply  # message count
    assert "token" in reply.lower()


# --- /usage + /cost ---------------------------------------------------------


def _fake_summary(monkeypatch, *, runs, prompt, completion, total):
    from fleetent.observability import usage as usage_mod

    s = usage_mod.UsageSummary(
        run_count=runs,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        total_elapsed_s=1.0,
        avg_elapsed_s=0.3,
        by_model=[],
    )
    monkeypatch.setattr(usage_mod, "get_usage_summary", lambda q: s)


async def test_usage_reports_tokens(monkeypatch) -> None:
    _fake_summary(monkeypatch, runs=3, prompt=100, completion=50, total=150)
    reply = await commands.handle_command(_ctx(session_id="s1"), "/usage")
    assert reply is not None
    assert "3" in reply and "150" in reply


async def test_cost_is_token_basis_with_disclaimer(monkeypatch) -> None:
    _fake_summary(monkeypatch, runs=1, prompt=80, completion=20, total=100)
    reply = await commands.handle_command(_ctx(session_id="s1"), "/cost")
    assert reply is not None
    assert "100" in reply
    assert "美元" in reply or "token" in reply.lower()  # explicit non-USD disclaimer
