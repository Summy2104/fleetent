import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

import mini_agent.permission_gate as permission_gate
from mini_agent.permission_gate import PermissionGate


@pytest.fixture
def db(tmp_path, monkeypatch):
    import mini_agent.user_store as user_store

    db_path = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", db_path)
    monkeypatch.setattr(permission_gate, "DB_PATH", db_path)
    permission_gate._init_db()
    return db_path


@pytest.fixture
def gate(db):
    return PermissionGate(
        medium_timeout=0.2,  # short for tests
        high_timeout=0.2,
    )


async def test_approved_path(gate, db):
    reply_func = AsyncMock()
    approval_id = "appr-1"

    async def approve_after_delay():
        await asyncio.sleep(0.05)
        await gate.resolve(approval_id, "approved", approver_user_id="approver-1")

    asyncio.create_task(approve_after_delay())
    result = await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={"to": "test@example.com"},
        requester_user_id="user-1",
        reply_func=reply_func,
    )
    assert result == "approved"
    reply_func.assert_called_once()


async def test_rejected_path(gate, db):
    reply_func = AsyncMock()
    approval_id = "appr-2"

    async def reject_after_delay():
        await asyncio.sleep(0.05)
        await gate.resolve(approval_id, "rejected", approver_user_id="user-1")

    asyncio.create_task(reject_after_delay())
    result = await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
    )
    assert result == "rejected"


async def test_timeout_path(gate, db):
    reply_func = AsyncMock()
    result = await gate.request_approval(
        approval_id="appr-3",
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
    )
    assert result == "timeout"


async def test_approvals_table_updated(gate, db):
    reply_func = AsyncMock()
    approval_id = "appr-4"

    async def approve():
        await asyncio.sleep(0.02)
        await gate.resolve(approval_id, "approved", approver_user_id="approver-1")

    asyncio.create_task(approve())
    await gate.request_approval(
        approval_id=approval_id,
        risk_level="high",
        tool_name="delete_table",
        tool_args={"name": "users"},
        requester_user_id="user-1",
        reply_func=reply_func,
    )
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, approver_user_id FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "approved"
    assert row[1] == "approver-1"


async def test_timeout_sets_status_in_db(gate, db):
    reply_func = AsyncMock()
    approval_id = "appr-5"
    await gate.request_approval(
        approval_id=approval_id,
        risk_level="medium",
        tool_name="send_email",
        tool_args={},
        requester_user_id="user-1",
        reply_func=reply_func,
    )
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    conn.close()
    assert row[0] == "timeout"
