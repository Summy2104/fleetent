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


@pytest.fixture
def sdir(tmp_path, monkeypatch):
    """Isolate the agent-side session dir so todo persistence writes to tmp_path,
    and reset the no-session ephemeral fallback for test isolation."""
    import fleetent.session.manager as mgr
    import fleetent.tools.interaction_tools as it

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    it._ephemeral_todo.clear()
    return tmp_path


def test_todo_set_assigns_ids_and_pending(sdir):
    ctx = ToolContext(session_id="todo_s1")
    todo(action="set", items=["task A", "task B"], tool_context=ctx)
    out = todo(action="get", tool_context=ctx)
    assert "task A" in out and "task B" in out
    assert "pending" in out  # newly-set items default to pending


def test_todo_update_marks_in_progress(sdir):
    import fleetent.session.manager as mgr

    ctx = ToolContext(session_id="todo_up")
    todo(action="set", items=["only task"], tool_context=ctx)
    item_id = mgr.read_todo("todo_up")[0]["id"]
    todo(action="update", item_id=item_id, status="in_progress", tool_context=ctx)
    assert mgr.read_todo("todo_up")[0]["status"] == "in_progress"


def test_todo_single_in_progress_rejected(sdir):
    import fleetent.session.manager as mgr

    ctx = ToolContext(session_id="todo_single")
    todo(action="set", items=["a", "b"], tool_context=ctx)
    items = mgr.read_todo("todo_single")
    todo(action="update", item_id=items[0]["id"], status="in_progress", tool_context=ctx)
    result = todo(action="update", item_id=items[1]["id"], status="in_progress", tool_context=ctx)
    # second in_progress rejected; item b stays pending
    assert mgr.read_todo("todo_single")[1]["status"] == "pending"
    assert "in_progress" in result or "进行中" in result  # guidance message


def test_todo_update_complete(sdir):
    import fleetent.session.manager as mgr

    ctx = ToolContext(session_id="todo_done")
    todo(action="set", items=["x"], tool_context=ctx)
    item_id = mgr.read_todo("todo_done")[0]["id"]
    todo(action="update", item_id=item_id, status="completed", tool_context=ctx)
    assert mgr.read_todo("todo_done")[0]["status"] == "completed"


def test_todo_update_unknown_id_errors(sdir):
    ctx = ToolContext(session_id="todo_unknown")
    todo(action="set", items=["x"], tool_context=ctx)
    result = todo(action="update", item_id="nope", status="completed", tool_context=ctx)
    assert "error" in result.lower() or "未找到" in result


def test_todo_clear_deletes_file(sdir):
    ctx = ToolContext(session_id="todo_clr")
    todo(action="set", items=["item 1"], tool_context=ctx)
    assert (sdir / "todo_clr.todo").exists()
    todo(action="clear", tool_context=ctx)
    assert not (sdir / "todo_clr.todo").exists()
    out = todo(action="get", tool_context=ctx)
    assert "空" in out or "empty" in out.lower()


def test_todo_session_isolation(sdir):
    ctx1 = ToolContext(session_id="iso_s1")
    ctx2 = ToolContext(session_id="iso_s2")
    todo(action="set", items=["only_for_s1"], tool_context=ctx1)
    out2 = todo(action="get", tool_context=ctx2)
    assert "only_for_s1" not in out2


def test_todo_get_empty(sdir):
    ctx = ToolContext(session_id="empty_todo_xyz")
    out = todo(action="get", tool_context=ctx)
    assert "空" in out or "empty" in out.lower()


def test_todo_set_replaces_existing(sdir):
    ctx = ToolContext(session_id="replace_s")
    todo(action="set", items=["old"], tool_context=ctx)
    todo(action="set", items=["new1", "new2"], tool_context=ctx)
    out = todo(action="get", tool_context=ctx)
    assert "old" not in out and "new1" in out and "new2" in out


def test_todo_persists_to_file(sdir):
    import fleetent.session.manager as mgr

    ctx = ToolContext(session_id="persist_s")
    todo(action="set", items=["keep me"], tool_context=ctx)
    # Authoritative state survives on disk (cross-restart): read directly from file.
    items = mgr.read_todo("persist_s")
    assert len(items) == 1 and items[0]["text"] == "keep me"


def test_todo_no_session_degrades_in_memory(sdir):
    # No session_id → in-memory temp list, no file written.
    ctx = ToolContext(session_id=None)
    todo(action="set", items=["ephemeral"], tool_context=ctx)
    out = todo(action="get", tool_context=ctx)
    assert "ephemeral" in out
    assert list(sdir.glob("*.todo")) == []


async def test_todo_under_session_lock_no_deadlock(sdir):
    import fleetent.session.manager as mgr

    ctx = ToolContext(session_id="locked_sess")
    # The tool runs inside the agent loop, which on the IM path already holds the
    # session lock for the whole run. The tool's persistence MUST be lock-free or
    # this re-entry would deadlock. Guard with a timeout so a regression fails fast.
    async with mgr.session_lock("locked_sess"):
        await asyncio.wait_for(
            asyncio.to_thread(todo, action="set", items=["x"], tool_context=ctx),
            timeout=2.0,
        )
    assert mgr.read_todo("locked_sess")[0]["text"] == "x"


def test_todo_schema_has_action_and_items():
    from fleetent.tools import registry as tr

    schemas = tr.get_schemas()
    schema = next((s for s in schemas if s["function"]["name"] == "todo"), None)
    assert schema is not None
    props = schema["function"]["parameters"]["properties"]
    assert "items" in props and props["items"]["type"] == "array"
    assert "action" in props
    assert set(props["action"]["enum"]) == {"set", "update", "get", "clear"}
