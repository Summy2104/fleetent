import asyncio
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
    return PermissionGate(
        medium_timeout=0.2,
        high_timeout=0.2,
    )


async def test_approved_path(gate, db, _mock_outbound):
    reply_func = AsyncMock()
    approval_id = "appr-1"

    async def approve_after_delay():
        await asyncio.sleep(0.05)
        await gate.resolve(approval_id, "approved", approver_user_id="U_APPROVER")

    asyncio.create_task(approve_after_delay())
    result = await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={"to": "test@example.com"},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "approved"
    reply_func.assert_called()


async def test_rejected_path(gate, db, _mock_outbound):
    reply_func = AsyncMock()
    approval_id = "appr-2"

    async def reject_after_delay():
        await asyncio.sleep(0.05)
        await gate.resolve(approval_id, "rejected", approver_user_id="U_APPROVER")

    asyncio.create_task(reject_after_delay())
    result = await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "rejected"


async def test_timeout_path(gate, db, _mock_outbound):
    """No resolve before timeout → gate returns 'timeout'."""
    reply_func = AsyncMock()
    result = await gate.request_approval(
        approval_id="appr-3",
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    assert result == "timeout"


async def test_approvals_table_updated(gate, db, _mock_outbound):
    reply_func = AsyncMock()
    approval_id = "appr-4"

    async def approve():
        await asyncio.sleep(0.02)
        await gate.resolve(approval_id, "approved", approver_user_id="U_APPROVER")

    asyncio.create_task(approve())
    await gate.request_approval(
        approval_id=approval_id,
        risk_level="high",
        tool_name="delete_table",
        tool_args={"name": "users"},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("high"),
        outbound_connectors=_connectors(),
    )
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, approver_actor FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "approved"
    # approver_actor is set from gate.resolve(approver_user_id=...) call
    assert row[1] == "U_APPROVER"


async def test_timeout_sets_status_in_db(gate, db, _mock_outbound):
    reply_func = AsyncMock()
    approval_id = "appr-5"
    await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    conn.close()
    assert row[0] == "timeout"


# ── per-call timeout override tests ──────────────────────────────────────────


async def test_medium_timeout_override_auto_rejects(db, _mock_outbound):
    """medium_timeout kwarg overrides instance default; auto-rejects after override value."""
    gate_long = PermissionGate(medium_timeout=300.0, high_timeout=3600.0)
    reply_func = AsyncMock()

    result = await gate_long.request_approval(
        approval_id="override-01",
        risk_level="medium",
        tool_name="write_file",
        tool_args={"path": "/tmp/x"},
        requester_user_id="user1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
        medium_timeout=0.05,
    )

    assert result == "timeout"
    reply_func.assert_called()


async def test_high_timeout_override_auto_rejects(db, _mock_outbound):
    """high_timeout kwarg overrides instance default for high-risk tools."""
    gate_long = PermissionGate(medium_timeout=300.0, high_timeout=3600.0)
    reply_func = AsyncMock()

    result = await gate_long.request_approval(
        approval_id="override-02",
        risk_level="high",
        tool_name="bash_exec",
        tool_args={"command": "ls"},
        requester_user_id="user1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("high"),
        outbound_connectors=_connectors(),
        high_timeout=0.05,
    )

    assert result == "timeout"


async def test_no_override_uses_instance_default(db, _mock_outbound):
    """Without override kwargs, short instance default still applies (behaviour unchanged)."""
    gate_short = PermissionGate(medium_timeout=0.05, high_timeout=3600.0)
    reply_func = AsyncMock()

    result = await gate_short.request_approval(
        approval_id="override-03",
        risk_level="medium",
        tool_name="write_file",
        tool_args={},
        requester_user_id="user1",
        reply_func=reply_func,
        session_id="test-session",
        approval_routing=_routing("medium"),
        outbound_connectors=_connectors(),
    )

    assert result == "timeout"
