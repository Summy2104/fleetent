"""Integration test: standalone agent approval e2e without platform (task 4.3).

Verifies that the full approval flow works without any platform DB tables present:
- Real approval_store writes to an isolated tmp_path SQLite DB.
- LLM calls are mocked (no real API).
- Outbound DM is mocked (no real Slack/Telegram).
- Approval resolved via PermissionGate.resolve() (same code path as POST /approvals/{id}/resolve).
- Persisted record has correct session_id, status, and opaque actor.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.governance.approval_store as approval_store_mod
# Patch the real module: permission_gate imports from fleetent.outbound; patching
# the fleetent.im_gateway.outbound re-export shim would not take effect.
import fleetent.outbound as outbound_mod
import fleetent.runtime.loop as loop_mod
from fleetent.agent_config import ApprovalRouting
from fleetent.governance.permission_gate import PermissionGate


# ── LLM stub helpers ─────────────────────────────────────────────────────────


def _stub_tool_then_stop(tool_name: str):
    """Return an async callable that yields one tool call then a text stop."""
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps({})

    msg_tool = MagicMock()
    msg_tool.content = None
    msg_tool.tool_calls = [tc]
    msg_tool.refusal = None
    choice_tool = MagicMock()
    choice_tool.message = msg_tool
    choice_tool.finish_reason = "tool_calls"
    resp_tool = MagicMock()
    resp_tool.choices = [choice_tool]
    resp_tool.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    msg_done = MagicMock()
    msg_done.content = "done"
    msg_done.tool_calls = None
    msg_done.refusal = None
    choice_done = MagicMock()
    choice_done.message = msg_done
    choice_done.finish_reason = "stop"
    resp_done = MagicMock()
    resp_done.choices = [choice_done]
    resp_done.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    seq = [resp_tool, resp_done]
    idx = [0]

    async def _create(**kwargs):
        r = seq[idx[0]]
        idx[0] += 1
        return r

    return _create


@pytest.fixture()
def _loop_env(monkeypatch):
    """Minimal loop env: fake LLM client, no real tool dispatch."""
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


# ── integration test ──────────────────────────────────────────────────────────


async def test_standalone_approval_no_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _loop_env
) -> None:
    """End-to-end approval: no platform tables, real agent-side store, mock outbound."""
    db_path = tmp_path / "agent.db"
    # Redirect approval_store DB to tmp_path — no platform tables exist or are needed.
    monkeypatch.setattr(approval_store_mod, "DB_PATH", db_path)

    # Mock outbound: all sends succeed, all targets reachable.
    monkeypatch.setattr(outbound_mod, "send_to", AsyncMock(return_value=True))
    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))

    # Fresh gate so shared state from other tests doesn't leak.
    gate = PermissionGate(high_timeout=2.0)
    monkeypatch.setattr(loop_mod, "_default_gate", gate)

    # LLM: tool call → text stop.
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "high")
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="dispatched"))
    _loop_env.chat.completions.create = _stub_tool_then_stop("delete_db")

    routing = ApprovalRouting(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}}
    )
    connector = AsyncMock()
    # Simulated approver resolves after outbound DM is sent.
    captured_id: list[str] = []

    original_send = outbound_mod.send_to

    async def _intercept_send(platform, connector_obj, target, text):
        # Extract approval_id from the DM text and schedule a resolve.
        import re

        m = re.search(r"`([a-f0-9-]{6,36})`", text)
        if m:
            captured_id.append(m.group(1))
            asyncio.get_event_loop().call_later(
                0.05,
                lambda: asyncio.ensure_future(
                    gate.resolve(captured_id[0], "approved", "slack:U_LEAD")
                ),
            )
        return True

    monkeypatch.setattr(outbound_mod, "send_to", _intercept_send)

    reply_calls: list[str] = []

    async def reply(text: str) -> None:
        reply_calls.append(text)

    await loop_mod.run(
        messages=[{"role": "user", "content": "delete the db"}],
        reply_func=reply,
        permission_gate_enabled=True,
        session_id="session:alice",
        approval_routing=routing,
        outbound_connectors={"slack": connector},
        permission_gate_high_timeout=1.0,
    )

    # Verify real approval_store was written — no platform DB needed.
    approvals = approval_store_mod.list_approvals(db_path=db_path)
    assert len(approvals) == 1
    rec = approvals[0]
    assert rec["status"] == "approved"
    assert rec["session_id"] == "session:alice"
    assert rec["approver_actor"] == "slack:U_LEAD"
    assert rec["tool_name"] == "delete_db"
    assert rec["resolved_at"] is not None

    # Requester got waiting notice (not an immediate rejection).
    assert any("⏳" in r for r in reply_calls)
    assert not any("❌" in r for r in reply_calls)

    # Tool was dispatched after approval.
    loop_mod.dispatch.assert_called_once()
