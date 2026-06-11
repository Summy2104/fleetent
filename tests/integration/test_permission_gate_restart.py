"""Restart survival for the permission gate (approval-suspend-resume Task 5).

After a process restart the gate's in-memory registry is empty, but the approvals
row persists. resolve() must still finalize a genuinely-pending approval, with
authorization recovered from the caller-supplied (persisted) approver set.
"""

import datetime
from pathlib import Path

import pytest

import fleetent.governance.approval_allowlist_store as approval_allowlist_store
import fleetent.governance.approval_store as approval_store
from fleetent.db import SQLiteDatabase
from fleetent.governance.permission_gate import PermissionGate
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture
def db(tmp_path: Path, monkeypatch):
    state_db = SQLiteDatabase(path=tmp_path / "agent.db")
    migrate(state_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(approval_store, "_state_db", state_db)
    monkeypatch.setattr(approval_allowlist_store, "_state_db", state_db)
    return state_db


def _insert_pending(approval_id: str) -> None:
    approval_store.insert_approval(
        id=approval_id,
        session_id="slack:dm:U_REQ:1.1",
        requester_user_id="U_REQ",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args="{}",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )


async def test_resolve_after_restart_finalizes_pending(db):
    _insert_pending("a1")
    # Fresh gate = post-restart: no in-memory _pending / _authorized.
    gate = PermissionGate()

    ok = await gate.resolve("a1", "approved", approver_user_id="U_REQ", authorized_actors={"U_REQ"})

    assert ok is True
    row = approval_store.get_approval("a1")
    assert row["status"] == "approved"
    assert row["approver_actor"] == "U_REQ"


async def test_resolve_after_restart_rejects_unauthorized_actor(db):
    _insert_pending("a2")
    gate = PermissionGate()

    ok = await gate.resolve(
        "a2", "approved", approver_user_id="U_OTHER", authorized_actors={"U_REQ"}
    )

    assert ok is False
    # Still pending — an unauthorized actor cannot finalize it.
    assert approval_store.get_approval("a2")["status"] == "pending"


async def test_resolve_after_restart_unknown_id_is_false(db):
    gate = PermissionGate()
    ok = await gate.resolve(
        "ghost", "approved", approver_user_id="U_REQ", authorized_actors={"U_REQ"}
    )
    assert ok is False


async def test_resolve_already_resolved_is_false(db):
    _insert_pending("a3")
    gate = PermissionGate()
    assert await gate.resolve("a3", "approved", "U_REQ", authorized_actors={"U_REQ"}) is True
    # Second resolve finds it non-pending in the store → False (idempotent guard).
    assert await gate.resolve("a3", "rejected", "U_REQ", authorized_actors={"U_REQ"}) is False


# ── expiry reconciliation (approval-suspend-resume Task 6) ────────────────────


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    import fleetent.session.manager as session_mgr

    d = tmp_path / "sessions"
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", d)
    return d


def _insert_pending_at(approval_id: str, session_id: str, created_at: str) -> None:
    approval_store.insert_approval(
        id=approval_id,
        session_id=session_id,
        requester_user_id="U_REQ",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args="{}",
        created_at=created_at,
    )


async def test_reconcile_times_out_only_expired_and_clears_meta(db, sessions_dir):
    import datetime

    import fleetent.session.manager as session_mgr
    from fleetent.runtime.approval_resume import reconcile_expired_approvals

    now = datetime.datetime.now(datetime.UTC)
    old = (now - datetime.timedelta(hours=48)).isoformat()
    fresh = now.isoformat()

    sid = "slack:dm:U_REQ:1.1"
    await session_mgr.save(sid, [{"role": "user", "content": "x"}])
    _insert_pending_at("expired", sid, old)
    _insert_pending_at("active", sid, fresh)
    await session_mgr.add_pending_approval(sid, "expired", {"tool_name": "send_im_message"})
    await session_mgr.add_pending_approval(sid, "active", {"tool_name": "send_im_message"})

    n = await reconcile_expired_approvals(expiry_seconds=24 * 3600)

    assert n == 1
    assert approval_store.get_approval("expired")["status"] == "timeout"
    assert approval_store.get_approval("active")["status"] == "pending"
    # Expired session entry cleared; active one preserved (survives for resume).
    remaining = await session_mgr.list_pending_approvals(sid)
    assert "expired" not in remaining
    assert "active" in remaining
