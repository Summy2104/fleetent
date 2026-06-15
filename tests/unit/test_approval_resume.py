"""Unit tests for resume_pending_approval (approval-suspend-resume Task 4).

Core orchestration: look up the pending entry, execute-or-decline the gated tool,
inject the outcome as context, clear the pending entry, and continue the run.
session_mgr and tool dispatch are mocked (no real files / tools).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

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

    monkeypatch.setattr(ar.session_mgr, "get_pending_approval", AsyncMock(return_value=dict(entry)))

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


async def test_execute_tool_dict_args_does_not_crash_on_summary():
    """Regression (fix-approval-resume-serialization): resume executes a tool with a DICT
    args entry; dispatch injects tool_context. The post-execution tool_call summary MUST NOT
    crash on the injected ToolContext, and the args entry stays clean."""
    import fleetent.runtime.approval_resume as ar
    from fleetent.tools import registry as tool_registry
    from fleetent.tools.registry import ToolContext

    @tool_registry.tool
    def resume_probe(target: str, tool_context=None) -> str:
        """opt-in tool exercised on the resume path."""
        return f"sent to {target}"

    args = {"target": "U2"}
    ctx = ToolContext(agent_name="a", session_id="s1")
    # _execute_tool dispatches then records the tool_call (build_tool_args_summary in finally).
    result = await ar._execute_tool("resume_probe", args, ctx, "tc1")

    assert result == "sent to U2"
    assert "tool_context" not in args  # caller's entry args not polluted
    # And the args summary built over those args is ToolContext-free + serializable.
    from fleetent.observability import build_tool_args_summary

    assert "ToolContext" not in build_tool_args_summary(args)


async def test_resumed_send_receipt_flows_to_continuation_trailer(_seeded, monkeypatch):
    """A shared delivery ledger lets the approved send's receipt reach the continuation's
    trailer — the deterministic '📬 实际投递' confirmation, not left to the model."""
    from fleetent.observability.traces import render_delivery_trailer
    from fleetent.outbound import DeliveryReceipt

    ar, entry, removed = _seeded
    shared_ledger: list[object] = []
    ctx = ToolContext(outbound_connectors={"slack": object()}, delivery_ledger=shared_ledger)

    def fake_dispatch(name, args, **kw):
        # Mirror _record_delivery: the executed send appends its receipt to the ctx ledger.
        kw["tool_context"].delivery_ledger.append(
            DeliveryReceipt(ok=True, platform="slack", target="U2", target_type="user", kind="text")
        )
        return "已发送私信到 slack:U2"

    monkeypatch.setattr(ar, "dispatch", fake_dispatch)

    async def continue_run(msgs):
        # Production continue_run is agent_loop.run sharing this SAME ledger; emulate the
        # finalize trailer render over it.
        base = "好的，已帮你发出。"
        trailer = render_delivery_trailer(shared_ledger)
        return f"{base}\n\n{trailer}" if trailer else base

    reply = await resume_pending_approval(
        session_id="slack:dm:U_REQ:1.1",
        approval_id="a1",
        decision="approved",
        messages=[],
        tool_context=ctx,
        continue_run=continue_run,
    )

    assert len(shared_ledger) == 1  # the resumed send recorded into the shared ledger
    assert "📬 实际投递" in reply
    assert "消息" in reply


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
