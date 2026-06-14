"""Integration tests: unified approval schema migrates into per-agent agent_state.db.

Verifies that after Y migration the agent_state.db contains `approval_requests` and
`tool_auto_approvals` tables with correct columns, and that opening the same DB
twice is idempotent (no SchemaTooNewError).
"""

from __future__ import annotations

from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def test_approval_requests_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {
        r["name"]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "approval_requests" in tables, (
        "approval_requests table must be created by agent_state MIGRATIONS"
    )


def test_tool_auto_approvals_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {
        r["name"]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "tool_auto_approvals" in tables, (
        "tool_auto_approvals table must be created by agent_state MIGRATIONS"
    )


def test_approval_requests_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approval_requests)").fetchall()}
    required = {
        "id",
        "subject_type",
        "subject_id",
        "requester_user_id",
        "risk",
        "status",
        "approver_user_id",
        "decided_at",
        "reason",
        "routing_key",
        "created_at",
        "expires_at",
    }
    assert required.issubset(cols), f"approval_requests missing columns: {required - cols}"


def test_tool_auto_approvals_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(tool_auto_approvals)").fetchall()}
    required = {"fingerprint", "scope_key", "tool_name", "created_at", "created_by"}
    assert required.issubset(cols), f"tool_auto_approvals missing columns: {required - cols}"


def test_consecutive_open_state_db_is_idempotent(tmp_path: Path) -> None:
    """Opening agent_state.db twice must not raise SchemaTooNewError."""
    db_path = tmp_path / "agent_state.db"
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)  # must not raise


def test_approval_requests_column_is_approver_user_id(tmp_path: Path) -> None:
    """After latest Y migration approval_requests must have approver_user_id."""
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approval_requests)").fetchall()}
    assert "approver_user_id" in cols, "approval_requests must have approver_user_id column"
