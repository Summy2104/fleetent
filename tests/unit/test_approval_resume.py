"""Unit tests for resume_pending_approval (approval-suspend-resume Task 4).

Core orchestration: look up the pending entry, execute-or-decline the gated tool,
inject the outcome as context, clear the pending entry, and continue the run.
session_mgr and tool dispatch are mocked (no real files / tools).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.runtime.approval_resume import resume_pending_approval
from fleetent.tools.registry import ToolContext


@pytest.fixture
def _seeded(monkeypatch):
    import fleetent.runtime.approval_resume as ar

    entry = {
        "approval_id": "a1",
        "tool_call_id": "tc_1",
        "tool_name": "send_im_message",
        "tool_args": {"target": "U2", "text": "hi"},
        "risk": "medium",
        "approver_ids": ["U_REQ"],
    }
    removed: list[str] = []

    monkeypatch.setattr(
        ar.session_mgr, "get_pending_approval", AsyncMock(return_value=dict(entry))
    )

    async def fake_remove(sid, aid):
        removed.append(aid)

    monkeypatch.setattr(ar.session_mgr, "remove_pending_approval", fake_remove)
    return ar, entry, removed


async def test_approve_executes_tool_injects_result_and_continues(_seeded, monkeypatch):
    ar, entry, removed = _seeded
    connector = object()
    ctx = ToolContext(outbound_connectors={"slack": connector})

    dispatched: dict = {}

    def fake_dispatch(name, args, **kw):
        dispatched["name"] = name
        dispatched["args"] = args
        dispatched["tool_context"] = kw.get("tool_context")
        return "已发送私信到 slack:U2"

    monkeypatch.setattr(ar, "dispatch", fake_dispatch)

    messages: list[dict] = []

    async def continue_run(msgs):
        return "好的，已帮你发出。"

    reply = await resume_pending_approval(
        session_id="slack:dm:U_REQ:1.1",
        approval_id="a1",
        decision="approved",
        messages=messages,
        tool_context=ctx,
        continue_run=continue_run,
    )

    assert dispatched["name"] == "send_im_message"
    assert dispatched["tool_context"].outbound_connectors["slack"] is connector
    # outcome injected as a context message before continuing
    assert any("已批准" in m["content"] and "已发送私信" in m["content"] for m in messages)
    assert removed == ["a1"]
    assert reply == "好的，已帮你发出。"


async def test_reject_skips_execution_injects_decline_and_continues(_seeded, monkeypatch):
    ar, entry, removed = _seeded

    called = {"dispatched": False}

    def fake_dispatch(name, args, **kw):
        called["dispatched"] = True
        return "should not run"

    monkeypatch.setattr(ar, "dispatch", fake_dispatch)

    messages: list[dict] = []

    async def continue_run(msgs):
        return "已取消。"

    reply = await resume_pending_approval(
        session_id="slack:dm:U_REQ:1.1",
        approval_id="a1",
        decision="rejected",
        messages=messages,
        tool_context=ToolContext(),
        continue_run=continue_run,
    )

    assert called["dispatched"] is False
    assert any("拒绝" in m["content"] for m in messages)
    assert removed == ["a1"]
    assert reply == "已取消。"


async def test_missing_pending_is_noop_returns_none(monkeypatch):
    import fleetent.runtime.approval_resume as ar

    monkeypatch.setattr(ar.session_mgr, "get_pending_approval", AsyncMock(return_value=None))

    ran = {"continued": False}

    async def continue_run(msgs):
        ran["continued"] = True
        return "x"

    reply = await resume_pending_approval(
        session_id="s",
        approval_id="missing",
        decision="approved",
        messages=[],
        tool_context=ToolContext(),
        continue_run=continue_run,
    )

    assert reply is None
    assert ran["continued"] is False
