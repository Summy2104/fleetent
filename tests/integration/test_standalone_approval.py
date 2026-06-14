"""Integration test: standalone agent approval e2e without platform (3b-4).

Verifies that the full approval flow works without any platform DB tables present:
- Real approval_store writes to an isolated per-agent SQLite DB.
- LLM calls are mocked (no real API).
- Outbound DM is mocked (no real Slack/Telegram).
- Approval resolved via PermissionGate.resolve() (same code path as POST /approvals/{id}/resolve).
- Persisted record has correct session_id, status, and opaque actor.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.governance.approval_store as approval_store_mod
import fleetent.governance.tool_auto_approvals_store as allowlist_store_mod

# Patch the real module: permission_gate imports from fleetent.outbound; patching
# the fleetent.im_gateway.outbound re-export shim would not take effect.
import fleetent.outbound as outbound_mod
import fleetent.runtime.loop as loop_mod
from fleetent.agent_config import ApprovalRouting
from fleetent.db import SQLiteDatabase
from fleetent.governance.permission_gate import PermissionGate
from fleetent.outbound import DeliveryReceipt
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate

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
    # Inject a fresh per-agent state DB — no platform tables exist or are needed.
    state_db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(state_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(approval_store_mod, "_state_db", state_db)
    monkeypatch.setattr(allowlist_store_mod, "_state_db", state_db)

    # Mock outbound: all sends succeed, all targets reachable.
    monkeypatch.setattr(
        outbound_mod,
        "send_to",
        AsyncMock(
            return_value=DeliveryReceipt(
                ok=True, platform="slack", target="x", target_type="user", kind="text"
            )
        ),
    )
    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))

    # Fresh gate so shared state from other tests doesn't leak.
    gate = PermissionGate(high_timeout=2.0)
    monkeypatch.setattr(loop_mod, "_default_gate", gate)

    # LLM: tool call → text stop.
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "high")
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="dispatched"))
    _loop_env.chat.completions.create = _stub_tool_then_stop("delete_db")

    routing = ApprovalRouting(by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}})
    connector = AsyncMock()
    monkeypatch.setattr(
        outbound_mod,
        "send_to",
        AsyncMock(
            return_value=DeliveryReceipt(
                ok=True, platform="slack", target="x", target_type="user", kind="text"
            )
        ),
    )

    reply_calls: list[str] = []

    async def reply(text: str) -> None:
        reply_calls.append(text)

    # Suspend model: run() registers the approval and returns (no blocking wait); the
    # tool is NOT dispatched yet — it stays a placeholder until the decision resumes it.
    result = await loop_mod.run(
        messages=[{"role": "user", "content": "delete the db"}],
        reply_func=reply,
        permission_gate_enabled=True,
        session_id="session:alice",
        approval_routing=routing,
        outbound_connectors={"slack": connector},
        permission_gate_high_timeout=1.0,
    )
    assert result == ""  # suspended; the prompt was already sent by the gate

    # Real agent-side approval_store written, no platform DB — row is pending.
    approvals = approval_store_mod.list_approvals()
    assert len(approvals) == 1
    rec = approvals[0]
    assert rec["status"] == "pending"
    assert rec["session_id"] == "session:alice"
    assert rec["tool_name"] == "delete_db"
    loop_mod.dispatch.assert_not_called()  # not executed until resumed

    # Requester got a waiting notice (not an immediate rejection).
    assert any("⏳" in r for r in reply_calls)
    assert not any("❌" in r for r in reply_calls)

    # The approver resolves out-of-band → the store row is finalized to approved.
    ok = await gate.resolve(rec["id"], "approved", "slack:U_LEAD")
    assert ok is True
    finalized = approval_store_mod.list_approvals()[0]
    assert finalized["status"] == "approved"
    assert finalized["approver_user_id"] == "slack:U_LEAD"
    assert finalized["resolved_at"] is not None
