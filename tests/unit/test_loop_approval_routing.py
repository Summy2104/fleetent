"""Unit tests for loop.run() approval routing wiring (task 4.1/4.2).

Verifies:
- permission_gate_enabled=False skips approval entirely (existing behavior preserved).
- medium/high risk tools pass approval_routing + outbound_connectors + session_id to the gate.
- No "self-confirm" fallback: when no approver resolves, tool is rejected.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    """Patch approval_store so unit tests never touch real SQLite."""
    from fleetent.governance import approval_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(approval_store, "list_approvals", MagicMock(return_value=[]))
    monkeypatch.setattr(approval_store, "cleanup_stale", MagicMock(return_value=0))


@pytest.fixture()
def mock_loop_env(monkeypatch) -> MagicMock:
    """Standard loop mock: text LLM response, no real tools/dispatch."""
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


def _tool_response(tool_name: str) -> AsyncMock:
    """LLM stub: one tool call then text stop."""
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


# ── permission_gate_enabled=False skips gate entirely ────────────────────────


async def test_permission_gate_disabled_tool_dispatched(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """permission_gate_enabled=False: medium-risk tool dispatched without approval."""
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)

    mock_loop_env.chat.completions.create = _tool_response("write_file")

    await loop_mod.run(
        messages=[{"role": "user", "content": "write"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=False,
    )

    mock_dispatch.assert_called_once()


# ── approval_routing + session_id forwarded to gate ──────────────────────────


async def test_approval_routing_forwarded_to_gate(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """loop passes approval_routing, outbound_connectors, and session_id to request_approval."""
    from fleetent.agent_config import ApprovalRouting
    from fleetent.governance.permission_gate import PermissionGate

    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "high")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    mock_loop_env.chat.completions.create = _tool_response("delete_db")

    captured: dict = {}

    async def fake_request_approval(**kwargs):
        captured.update(kwargs)
        return "rejected"  # Gate rejects so dispatch is skipped

    gate = PermissionGate()
    monkeypatch.setattr(gate, "request_approval", fake_request_approval)
    monkeypatch.setattr(loop_mod, "_default_gate", gate)

    routing = ApprovalRouting(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}}
    )
    connectors = {"slack": AsyncMock()}

    await loop_mod.run(
        messages=[{"role": "user", "content": "delete the db"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        session_id="user:alice",
        approval_routing=routing,
        outbound_connectors=connectors,
        permission_gate_high_timeout=0,
    )

    assert captured.get("approval_routing") is routing
    assert captured.get("outbound_connectors") is connectors
    assert captured.get("session_id") == "user:alice"


# ── no "self-confirm" fallback for medium/high ────────────────────────────────


async def test_medium_no_approver_is_rejected_not_self_confirmed(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """medium risk with no approver config → gate rejects (not self-confirm fallback)."""
    from fleetent.agent_config import ApprovalRouting

    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "medium")
    monkeypatch.setattr(loop_mod, "dispatch", mock_dispatch)
    mock_loop_env.chat.completions.create = _tool_response("run_code")

    # Routing with no medium entry → no approver → default-closed reject
    routing = ApprovalRouting(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}}
    )

    await loop_mod.run(
        messages=[{"role": "user", "content": "run some code"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        session_id="user:bob",
        approval_routing=routing,
        outbound_connectors={},
        permission_gate_medium_timeout=0,
    )

    # Tool was rejected (not dispatched) — no self-confirm fallback
    mock_dispatch.assert_not_called()
