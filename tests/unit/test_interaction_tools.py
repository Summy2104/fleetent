"""Tests for clarify and todo (builtin-interaction-tools spec)."""

from __future__ import annotations

import asyncio

import pytest

from fleetent.tools.interaction_tools import clarify, todo
from fleetent.tools.registry import ToolContext


# ── clarify ───────────────────────────────────────────────────────────────────


async def test_clarify_returns_user_answer(monkeypatch):
    import fleetent.governance.user_input_gate as uig
    session = "test_session_clarify"

    async def _answer():
        await asyncio.sleep(0.05)
        uig.answer(session, "yes")

    asyncio.create_task(_answer())
    ctx = ToolContext(session_id=session)
    result = await clarify(
        question="Do you want to continue?",
        tool_context=ctx,
        timeout=2.0,
    )
    assert result == "yes"


async def test_clarify_timeout_returns_timeout_string():
    ctx = ToolContext(session_id="timeout_session_xyz")
    result = await clarify(
        question="Will you answer?",
        tool_context=ctx,
        timeout=0.05,
    )
    assert "timeout" in result.lower() or "超时" in result


async def test_clarify_open_ended_no_choices(monkeypatch):
    import fleetent.governance.user_input_gate as uig
    session = "open_session"

    async def _reply():
        await asyncio.sleep(0.02)
        uig.answer(session, "free text answer")

    asyncio.create_task(_reply())
    ctx = ToolContext(session_id=session)
    result = await clarify(question="What is your goal?", tool_context=ctx, timeout=2.0)
    assert result == "free text answer"


async def test_clarify_with_choices_records_question(monkeypatch):
    import fleetent.governance.user_input_gate as uig
    session = "choices_session"

    async def _pick():
        await asyncio.sleep(0.02)
        uig.answer(session, "option_b")

    asyncio.create_task(_pick())
    ctx = ToolContext(session_id=session)
    result = await clarify(
        question="Pick one",
        choices=["option_a", "option_b"],
        tool_context=ctx,
        timeout=2.0,
    )
    assert result == "option_b"


async def test_clarify_without_context_uses_fallback_session():
    # No tool_context → uses a generated session key, will timeout
    result = await clarify(question="No context?", timeout=0.05)
    assert "timeout" in result.lower() or "超时" in result


# ── todo ──────────────────────────────────────────────────────────────────────


def test_todo_set_and_get():
    ctx = ToolContext(session_id="todo_s1")
    todo(action="set", items=["task A", "task B"], tool_context=ctx)
    result = todo(action="get", tool_context=ctx)
    assert "task A" in result
    assert "task B" in result


def test_todo_clear():
    ctx = ToolContext(session_id="todo_s2")
    todo(action="set", items=["item 1"], tool_context=ctx)
    todo(action="clear", tool_context=ctx)
    result = todo(action="get", tool_context=ctx)
    assert "item 1" not in result
    assert "空" in result or "empty" in result.lower()


def test_todo_session_isolation():
    ctx1 = ToolContext(session_id="iso_s1")
    ctx2 = ToolContext(session_id="iso_s2")
    todo(action="set", items=["only_for_s1"], tool_context=ctx1)
    result2 = todo(action="get", tool_context=ctx2)
    assert "only_for_s1" not in result2


def test_todo_get_empty():
    ctx = ToolContext(session_id="empty_todo_xyz")
    result = todo(action="get", tool_context=ctx)
    assert "空" in result or "empty" in result.lower()


def test_todo_set_replaces_existing():
    ctx = ToolContext(session_id="replace_s")
    todo(action="set", items=["old"], tool_context=ctx)
    todo(action="set", items=["new1", "new2"], tool_context=ctx)
    result = todo(action="get", tool_context=ctx)
    assert "old" not in result
    assert "new1" in result
    assert "new2" in result


def test_todo_schema_has_list_items():
    from fleetent.tools import registry as tr
    import fleetent.tools  # noqa: ensure registration
    schemas = tr.get_schemas()
    schema = next((s for s in schemas if s["function"]["name"] == "todo"), None)
    assert schema is not None
    props = schema["function"]["parameters"]["properties"]
    assert "items" in props
    assert props["items"]["type"] == "array"
