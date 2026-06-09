"""Integration tests for the agent-side approval store (task 3.1/3.2).

Verifies ensure_schema, CRUD, named params, correct session_id, and
absence of sqlite3.connect / user_store._conn in the module source.
"""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from fleetent.governance import approval_store


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "approvals_test.db"


# ── ensure_schema ──────────────────────────────────────────────────────────────


def test_ensure_schema_creates_approvals_table(db_path) -> None:
    """ensure_schema creates the approvals table idempotently."""
    approval_store.ensure_schema(db_path)
    approval_store.ensure_schema(db_path)  # idempotent

    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "approvals" in tables


def test_ensure_schema_creates_required_columns(db_path) -> None:
    approval_store.ensure_schema(db_path)

    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(approvals)")}
    conn.close()

    required = {
        "id", "session_id", "requester_user_id", "risk_level",
        "tool_name", "tool_args", "status", "approver_actor",
        "created_at", "resolved_at",
    }
    assert required.issubset(cols)


# ── insert / update lifecycle ─────────────────────────────────────────────────


def test_insert_approval_creates_pending_record(db_path) -> None:
    approval_store.ensure_schema(db_path)

    approval_store.insert_approval(
        id="abc12345",
        session_id="user:alice",
        requester_user_id="alice",
        risk_level="high",
        tool_name="delete_db",
        tool_args='{"table": "users"}',
        created_at="2026-01-01T00:00:00+00:00",
        db_path=db_path,
    )

    rows = approval_store.list_approvals(db_path=db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "abc12345"
    assert row["session_id"] == "user:alice"
    assert row["status"] == "pending"
    assert row["tool_name"] == "delete_db"


def test_insert_approval_records_non_empty_session_id(db_path) -> None:
    """session_id must be the actual session, not an empty string (bug fix)."""
    approval_store.ensure_schema(db_path)

    approval_store.insert_approval(
        id="sess_fix",
        session_id="user:bob",
        requester_user_id="bob",
        risk_level="medium",
        tool_name="run_code",
        tool_args="{}",
        created_at="2026-01-01T00:00:00+00:00",
        db_path=db_path,
    )

    rows = approval_store.list_approvals(db_path=db_path)
    assert rows[0]["session_id"] == "user:bob"
    assert rows[0]["session_id"] != ""


def test_update_approval_sets_status_and_actor(db_path) -> None:
    approval_store.ensure_schema(db_path)
    approval_store.insert_approval(
        id="upd_test",
        session_id="s1",
        requester_user_id="u1",
        risk_level="high",
        tool_name="tool_x",
        tool_args="{}",
        created_at="2026-01-01T00:00:00+00:00",
        db_path=db_path,
    )

    approval_store.update_approval(
        id="upd_test",
        status="approved",
        resolved_at="2026-01-01T01:00:00+00:00",
        approver_actor="slack:U_APPROVER",
        db_path=db_path,
    )

    rows = approval_store.list_approvals(db_path=db_path)
    assert rows[0]["status"] == "approved"
    assert rows[0]["approver_actor"] == "slack:U_APPROVER"
    assert rows[0]["resolved_at"] is not None


def test_list_approvals_filters_by_status(db_path) -> None:
    approval_store.ensure_schema(db_path)
    for id_, status in [("p1", None), ("p2", None)]:
        approval_store.insert_approval(
            id=id_,
            session_id="s",
            requester_user_id="u",
            risk_level="medium",
            tool_name="t",
            tool_args="{}",
            created_at="2026-01-01T00:00:00+00:00",
            db_path=db_path,
        )
    approval_store.update_approval(
        id="p1",
        status="approved",
        resolved_at="2026-01-01T01:00:00+00:00",
        db_path=db_path,
    )

    pending = approval_store.list_approvals(status="pending", db_path=db_path)
    approved = approval_store.list_approvals(status="approved", db_path=db_path)
    assert len(pending) == 1 and pending[0]["id"] == "p2"
    assert len(approved) == 1 and approved[0]["id"] == "p1"


# ── module boundary: no sqlite3.connect / user_store._conn ────────────────────


def test_approval_store_does_not_use_raw_sqlite3_connect() -> None:
    """Store must not call sqlite3.connect directly (use db.SQLiteDatabase)."""
    source = inspect.getsource(approval_store)
    assert "sqlite3.connect" not in source


def test_approval_store_does_not_import_user_store() -> None:
    """Store must not import from fleetent.user_store."""
    source = inspect.getsource(approval_store)
    assert "fleetent.user_store" not in source
    assert "user_store" not in source
