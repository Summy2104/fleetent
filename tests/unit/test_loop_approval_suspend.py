"""Loop suspends (does not block) when a gated tool call awaits approval.

approval-suspend-resume Task 3: _plan_run_slots writes an awaiting_human_approval
placeholder; run() ends with StopReason.awaiting_approval and persists the pending
mapping to the session. LLM client + stores are mocked; no real DB/HTTP.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.identity import Principal


def _requester_routing():
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(by_risk={"medium": {"approvers": ["requester"], "policy": "any"}})


def _governance():
    from fleetent.runtime.snapshot import GovernanceConfig

    return GovernanceConfig()


def _tool_call_response(name: str, args: str = "{}"):
    tc = MagicMock()
    tc.id = "tc_1"
    tc.function.name = name
    tc.function.arguments = args
    m = MagicMock()
    m.content = None
    m.tool_calls = [tc]
    m.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "tc_1", "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }
    ch = MagicMock()
    ch.finish_reason = "tool_calls"
    ch.message = m
    r = MagicMock()
    r.choices = [ch]
    r.usage = MagicMock()
    return r


@pytest.fixture
def _loop_env(monkeypatch):
    """Mock the LLM client + side-effect stores so run() is deterministic and offline."""
    import fleetent.runtime.loop as al
    from fleetent.governance import approval_store
    from fleetent.governance import tool_auto_approvals_store as allowlist

    captured: dict = {}

    async def fake_create(**kwargs):
        return _tool_call_response("send_im_message", '{"target": "U2", "text": "hi"}')

    def _client():
        c = AsyncMock()
        c.chat = MagicMock()
        c.chat.completions = MagicMock()
        c.chat.completions.create = AsyncMock(side_effect=fake_create)
        return c

    monkeypatch.setattr(
        al,
        "get_schemas",
        lambda: [{"type": "function", "function": {"name": "send_im_message", "parameters": {}}}],
    )
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **k: None)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _client())
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)

    def fake_log_run(*a, **kw):
        captured["stop_reason"] = kw.get("stop_reason")

    monkeypatch.setattr(al, "log_run", fake_log_run)

    # Stores: no real DB.
    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: False)

    # Capture pending persistence (loop → session_mgr).
    persisted: dict = {}

    async def fake_add_pending(session_id, approval_id, entry):
        persisted[approval_id] = {"session_id": session_id, **entry}

    monkeypatch.setattr(al.session_mgr, "add_pending_approval", fake_add_pending)

    return al, captured, persisted


async def test_run_suspends_with_placeholder_and_awaiting_stop(_loop_env):
    al, captured, persisted = _loop_env
    messages = [{"role": "user", "content": "send to U2"}]

    reply = await al.run(
        messages=messages,
        reply_func=AsyncMock(),
        principal=Principal(user_id="U_REQ", tenant_id="default"),
        session_id="slack:dm:U_REQ:1.1",
        governance=_governance(),
        approval_routing=_requester_routing(),
        permission_gate_enabled=True,
    )

    # Placeholder tool result keeps history valid (no dangling tool_call).
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert any("awaiting_human_approval" in str(m.get("content", "")) for m in tool_msgs)
    # Run ended on the non-terminal awaiting_approval reason.
    assert captured["stop_reason"].name == "awaiting_approval"
    # No second LLM turn / no final assistant text needed (prompt already sent by gate).
    assert reply == ""


async def test_run_persists_pending_mapping_to_session(_loop_env):
    al, captured, persisted = _loop_env
    messages = [{"role": "user", "content": "send to U2"}]

    await al.run(
        messages=messages,
        reply_func=AsyncMock(),
        principal=Principal(user_id="U_REQ", tenant_id="default"),
        session_id="slack:dm:U_REQ:1.1",
        governance=_governance(),
        approval_routing=_requester_routing(),
        permission_gate_enabled=True,
    )

    assert len(persisted) == 1
    entry = next(iter(persisted.values()))
    assert entry["tool_call_id"] == "tc_1"
    assert entry["tool_name"] == "send_im_message"
    assert entry["session_id"] == "slack:dm:U_REQ:1.1"
    assert "U_REQ" in entry["approver_ids"]


def _final_text_response(text: str = "天气晴。"):
    m = MagicMock()
    m.content = text
    m.tool_calls = None
    m.model_dump = lambda: {"role": "assistant", "content": text}
    ch = MagicMock()
    ch.finish_reason = "stop"
    ch.message = m
    r = MagicMock()
    r.choices = [ch]
    r.usage = MagicMock()
    return r


async def test_run_injects_outstanding_approval_note(monkeypatch):
    """When a pending approval exists, run injects awareness into the system prompt."""
    import fleetent.runtime.loop as al

    async def fake_create(**kwargs):
        return _final_text_response()

    def _client():
        c = AsyncMock()
        c.chat = MagicMock()
        c.chat.completions = MagicMock()
        c.chat.completions.create = AsyncMock(side_effect=fake_create)
        return c

    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "collect_disabled_trace", lambda *a, **k: None)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (50, 3),
    )
    monkeypatch.setattr(al, "_build_async_client", lambda r, k: _client())
    monkeypatch.setattr(al, "build_context", AsyncMock(return_value=MagicMock(text="", sources=[])))
    monkeypatch.setattr(al, "record_trace_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(
        al.session_mgr,
        "list_pending_approvals",
        AsyncMock(return_value={"a1": {"tool_name": "send_im_message"}}),
    )

    messages = [
        {"role": "system", "content": "you are a bot"},
        {"role": "user", "content": "天气?"},
    ]
    await al.run(
        messages=messages,
        principal=Principal(user_id="U_REQ", tenant_id="default"),
        session_id="slack:dm:U_REQ:1.1",
    )

    system = next(m for m in messages if m["role"] == "system")
    assert "等待人工审批" in system["content"]
    assert "send_im_message" in system["content"]
