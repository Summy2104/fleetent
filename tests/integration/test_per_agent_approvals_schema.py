"""Integration tests: approvals schema migrates into per-agent agent_state.db (3b-4).

Verifies that after Y migration the agent_state.db contains `approvals` and
`approval_allowlist` tables with correct columns, and that opening the same DB
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


def test_approvals_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "approvals" in tables, "approvals table must be created by agent_state MIGRATIONS"


def test_approval_allowlist_table_exists_after_migration(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "approval_allowlist" in tables, "approval_allowlist table must be created by agent_state MIGRATIONS"


def test_approvals_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approvals)").fetchall()}
    required = {
        "id", "session_id", "requester_user_id", "risk_level",
        "tool_name", "tool_args", "status", "approver_actor",
        "created_at", "resolved_at",
    }
    assert required.issubset(cols), f"approvals missing columns: {required - cols}"


def test_approval_allowlist_columns_match_store_schema(tmp_path: Path) -> None:
    db = _open_state_db(tmp_path)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(approval_allowlist)").fetchall()}
    required = {"fingerprint", "scope_key", "tool_name", "created_at", "created_by"}
    assert required.issubset(cols), f"approval_allowlist missing columns: {required - cols}"


def test_consecutive_open_state_db_is_idempotent(tmp_path: Path) -> None:
    """Opening agent_state.db twice must not raise SchemaTooNewError."""
    db_path = tmp_path / "agent_state.db"
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)  # must not raise
