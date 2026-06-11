"""Integration tests for the permission gate against a real approvals DB.

Rewritten for approval-suspend-resume: request_approval registers + returns "pending"
(non-blocking); resolve() finalizes the row. Blocking-timeout tests are gone — timeout
is now handled by reconcile_expired_approvals (see test_permission_gate_restart.py).
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import fleetent.governance.approval_allowlist_store as approval_allowlist_store
import fleetent.governance.approval_store as approval_store
import fleetent.im_gateway.outbound as outbound_mod
from fleetent.agent_config import ApprovalRouting
from fleetent.db import SQLiteDatabase
from fleetent.governance.permission_gate import PermissionGate
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _routing(risk: str = "medium") -> ApprovalRouting:
    return ApprovalRouting(by_risk={risk: {"approvers": ["slack:U_APPROVER"], "policy": "any"}})


def _connectors() -> dict:
    connector = AsyncMock()
    connector.conversations_open = AsyncMock(return_value={"channel": {"id": "DM"}})
    connector.chat_postMessage = AsyncMock(return_value={"ok": True})
    return {"slack": connector}


@pytest.fixture
def db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "agent.db"
    state_db = SQLiteDatabase(path=db_path)
    migrate(state_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(approval_store, "_state_db", state_db)
    monkeypatch.setattr(approval_allowlist_store, "_state_db", state_db)
    return db_path


@pytest.fixture
def _mock_outbound(monkeypatch):
    """Mock outbound so sends succeed and targets are reachable."""
    monkeypatch.setattr(outbound_mod, "send_to", AsyncMock(return_value=True))
    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))


@pytest.fixture
def gate(db):
    return PermissionGate()


def _status(db_path, approval_id):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, approver_actor FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    conn.close()
    return row


async def test_request_registers_pending_then_approve_finalizes(gate, db, _mock_outbound):
    reply_func = AsyncMock()
    result = await gate.request_approval(
        approval_id="appr-1",
        risk_level="medium",
        tool_name="send_email",
        tool_args={"to": "test@example.com"},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "pending"
    assert _status(db, "appr-1")[0] == "pending"
    reply_func.assert_called()

    ok = await gate.resolve("appr-1", "approved", approver_user_id="U_APPROVER")
    assert ok is True
    assert _status(db, "appr-1") == ("approved", "U_APPROVER")


async def test_request_then_reject_finalizes(gate, db, _mock_outbound):
    result = await gate.request_approval(
        approval_id="appr-2",
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=AsyncMock(),
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "pending"
    await gate.resolve("appr-2", "rejected", approver_user_id="U_APPROVER")
    assert _status(db, "appr-2")[0] == "rejected"


async def test_high_risk_table_reflects_decision(gate, db, _mock_outbound):
    await gate.request_approval(
        approval_id="appr-4",
        risk_level="high",
        tool_name="delete_table",
        tool_args={"name": "users"},
        requester_user_id="user-1",
        reply_func=AsyncMock(),
        session_id="test-session",
        approval_routing=_routing("high"),
        outbound_connectors=_connectors(),
    )
    await gate.resolve("appr-4", "approved", approver_user_id="U_APPROVER")
    assert _status(db, "appr-4") == ("approved", "U_APPROVER")


async def test_unresolved_request_stays_pending(gate, db, _mock_outbound):
    """Without a decision the approval stays pending (no blocking auto-timeout)."""
    result = await gate.request_approval(
        approval_id="appr-3",
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=AsyncMock(),
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "pending"
    assert _status(db, "appr-3")[0] == "pending"
