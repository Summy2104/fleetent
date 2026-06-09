"""Unit tests for Action Gate wiring in loop._plan_run_slots (action-gate, task 3).

Mocks the LLM (one tool call) and the gate; asserts the four-mode routing:
- CRITICAL → rejected, gate never consulted, tool never dispatched.
- medium/high default → still routed to approval (regression vs merged routing).
- medium_mode=sandbox + sandbox-backed tool → dispatched directly, no approval.
- medium_mode=sandbox + non-sandbox-backed tool → fail-closed to approval.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod
from fleetent.runtime.snapshot import GovernanceConfig


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    from fleetent.governance import approval_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(approval_store, "list_approvals", MagicMock(return_value=[]))
    monkeypatch.setattr(approval_store, "cleanup_stale", MagicMock(return_value=0))


@pytest.fixture()
def mock_loop_env(monkeypatch) -> MagicMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        loop_mod, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop_mod, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop_mod, "get_schemas", lambda: [])
    monkeypatch.setattr(loop_mod, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop_mod, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop_mod, "extract_and_update", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _tool_response(tool_name: str):
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps({})

    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
    choice1 = MagicMock()
    choice1.message = msg1
    choice1.finish_reason = "tool_calls"
    resp1 = MagicMock()
    resp1.choices = [choice1]
    resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    msg2 = MagicMock()
    msg2.content = "done"
    msg2.tool_calls = None
    msg2.refusal = None
    choice2 = MagicMock()
    choice2.message = msg2
    choice2.finish_reason = "stop"
    resp2 = MagicMock()
    resp2.choices = [choice2]
    resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    responses = [resp1, resp2]
    call_count = [0]

    async def _create(**kwargs):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r

    return _create


def _spy_gate(monkeypatch, result: str = "approved") -> dict:
    captured: dict = {"called": False}

    async def fake_request_approval(**kwargs):
        captured["called"] = True
        captured.update(kwargs)
        return result

    from fleetent.governance.permission_gate import PermissionGate

    gate = PermissionGate()
    monkeypatch.setattr(gate, "request_approval", fake_request_approval)
    monkeypatch.setattr(loop_mod, "_default_gate", gate)
    return captured


async def test_critical_tool_rejected_without_gate(mock_loop_env, monkeypatch) -> None:
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "critical")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = _spy_gate(monkeypatch)
    mock_loop_env.chat.completions.create = _tool_response("nuke_everything")

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
    )

    mock_dispatch.assert_not_called()
    assert gate["called"] is False


async def test_medium_default_routes_to_approval(mock_loop_env, monkeypatch) -> None:
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = _spy_gate(monkeypatch, result="approved")
    mock_loop_env.chat.completions.create = _tool_response("write_file")

    await loop_mod.run(
        messages=[{"role": "user", "content": "write"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
    )

    assert gate["called"] is True


async def test_sandbox_mode_backed_tool_skips_approval(mock_loop_env, monkeypatch) -> None:
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = _spy_gate(monkeypatch)
    mock_loop_env.chat.completions.create = _tool_response("run_code")

    await loop_mod.run(
        messages=[{"role": "user", "content": "run"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        governance=GovernanceConfig(action_gate_medium_mode="sandbox"),
    )

    assert gate["called"] is False
    mock_dispatch.assert_called_once()


async def test_sandbox_mode_non_backed_tool_fails_closed_to_approval(
    mock_loop_env, monkeypatch
) -> None:
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = _spy_gate(monkeypatch, result="approved")
    mock_loop_env.chat.completions.create = _tool_response("send_message")

    await loop_mod.run(
        messages=[{"role": "user", "content": "send"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        governance=GovernanceConfig(action_gate_medium_mode="sandbox"),
    )

    assert gate["called"] is True


# ── anti-escape: risk comes from the registry, not tool args ──────────────────


def _tool_response_with_args(tool_name: str, args: dict):
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(args)
    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
    choice1 = MagicMock()
    choice1.message = msg1
    choice1.finish_reason = "tool_calls"
    resp1 = MagicMock()
    resp1.choices = [choice1]
    resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    msg2 = MagicMock()
    msg2.content = "done"
    msg2.tool_calls = None
    msg2.refusal = None
    choice2 = MagicMock()
    choice2.message = msg2
    choice2.finish_reason = "stop"
    resp2 = MagicMock()
    resp2.choices = [choice2]
    resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    responses = [resp1, resp2]
    call_count = [0]

    async def _create(**kwargs):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r

    return _create


async def test_tool_args_cannot_downgrade_critical(mock_loop_env, monkeypatch) -> None:
    """LLM-supplied risk/risk_level in args must not relax a registry-critical tool."""
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "critical")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = _spy_gate(monkeypatch)
    mock_loop_env.chat.completions.create = _tool_response_with_args(
        "nuke", {"risk": "low", "risk_level": "none"}
    )

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
    )

    mock_dispatch.assert_not_called()
    assert gate["called"] is False


# ── no_reply → reject: unreachable approver blocks execution ──────────────────


async def test_no_approver_reachable_rejects(mock_loop_env, monkeypatch) -> None:
    from fleetent.agent_config import ApprovalRouting
    from fleetent.governance.permission_gate import PermissionGate

    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "high")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    gate = PermissionGate(medium_timeout=0.1, high_timeout=0.1)
    monkeypatch.setattr(loop_mod, "_default_gate", gate)
    mock_loop_env.chat.completions.create = _tool_response("delete_db")

    await loop_mod.run(
        messages=[{"role": "user", "content": "delete"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        session_id="user:x",
        approval_routing=ApprovalRouting(by_risk={}),  # no approver for any risk
        outbound_connectors={},
        permission_gate_high_timeout=0,
    )

    mock_dispatch.assert_not_called()
