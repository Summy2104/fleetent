"""Integration tests for the agent-side approval store (3b-4 set_state_db pattern).

Verifies CRUD, named params, and absence of sqlite3.connect / platform imports
in the module source.  Connection is injected via monkeypatch on _state_db.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.governance import approval_store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture()
def state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


@pytest.fixture(autouse=True)
def _inject_db(state_db: SQLiteDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_store, "_state_db", state_db)


# ── schema ────────────────────────────────────────────────────────────────────


def test_approvals_table_exists(state_db: SQLiteDatabase) -> None:
    tables = {
        r["name"]
        for r in state_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "approvals" in tables


def test_approvals_required_columns(state_db: SQLiteDatabase) -> None:
    cols = {r["name"] for r in state_db.execute("PRAGMA table_info(approvals)").fetchall()}
    required = {
        "id", "session_id", "requester_user_id", "risk_level",
        "tool_name", "tool_args", "status", "approver_actor",
        "created_at", "resolved_at",
    }
    assert required.issubset(cols)


# ── insert / update lifecycle ─────────────────────────────────────────────────


def test_insert_approval_creates_pending_record() -> None:
    approval_store.insert_approval(
        id="abc12345",
        session_id="user:alice",
        requester_user_id="alice",
        risk_level="high",
        tool_name="delete_db",
        tool_args='{"table": "users"}',
        created_at="2026-01-01T00:00:00+00:00",
    )

    rows = approval_store.list_approvals()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "abc12345"
    assert row["session_id"] == "user:alice"
    assert row["status"] == "pending"
    assert row["tool_name"] == "delete_db"


def test_insert_approval_records_non_empty_session_id() -> None:
    approval_store.insert_approval(
        id="sess_fix",
        session_id="user:bob",
        requester_user_id="bob",
        risk_level="medium",
        tool_name="run_code",
        tool_args="{}",
        created_at="2026-01-01T00:00:00+00:00",
    )

    rows = approval_store.list_approvals()
    assert rows[0]["session_id"] == "user:bob"
    assert rows[0]["session_id"] != ""


def test_update_approval_sets_status_and_actor() -> None:
    approval_store.insert_approval(
        id="upd_test",
        session_id="s1",
        requester_user_id="u1",
        risk_level="high",
        tool_name="tool_x",
        tool_args="{}",
        created_at="2026-01-01T00:00:00+00:00",
    )
    approval_store.update_approval(
        id="upd_test",
        status="approved",
        resolved_at="2026-01-01T01:00:00+00:00",
        approver_actor="slack:U_APPROVER",
    )

    rows = approval_store.list_approvals()
    assert rows[0]["status"] == "approved"
    assert rows[0]["approver_actor"] == "slack:U_APPROVER"
    assert rows[0]["resolved_at"] is not None


def test_list_approvals_filters_by_status() -> None:
    for id_ in ("p1", "p2"):
        approval_store.insert_approval(
            id=id_,
            session_id="s",
            requester_user_id="u",
            risk_level="medium",
            tool_name="t",
            tool_args="{}",
            created_at="2026-01-01T00:00:00+00:00",
        )
    approval_store.update_approval(
        id="p1",
        status="approved",
        resolved_at="2026-01-01T01:00:00+00:00",
    )

    pending = approval_store.list_approvals(status="pending")
    approved = approval_store.list_approvals(status="approved")
    assert len(pending) == 1 and pending[0]["id"] == "p2"
    assert len(approved) == 1 and approved[0]["id"] == "p1"


# ── module boundary ───────────────────────────────────────────────────────────


def test_approval_store_does_not_use_raw_sqlite3_connect() -> None:
    source = inspect.getsource(approval_store)
    assert "sqlite3.connect" not in source


def test_approval_store_does_not_import_user_store() -> None:
    source = inspect.getsource(approval_store)
    assert "fleetent.user_store" not in source
    assert "user_store" not in source
