"""Integration tests: facts / fact_edges / relation_clusters schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_migrated(tmp_path: Path) -> tuple[SQLiteDatabase, Path]:
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db, db_path


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def _fetch_all(db_path: Path, sql: str) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def test_facts_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "memory_items" in _tables(db_path)
    assert "facts" not in _tables(db_path)


def test_fact_edges_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "fact_edges" in _tables(db_path)


def test_relation_clusters_table_exists_after_migration(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    assert "relation_clusters" in _tables(db_path)


def test_facts_columns_complete(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    cols = _columns(db_path, "memory_items")
    expected = {
        "fact_id",
        "user_id",
        "subject",
        "relation",
        "object",
        "cardinality",
        "status",
        "access_count",
        "first_accessed_at",
        "last_accessed_at",
        "expires_at",
        "valid_until",
        "created_at",
        "updated_at",
        "source_turn",
        "statement",
        "scope",
    }
    assert expected <= cols


def test_relation_clusters_preset_rows_exist(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    rows = _fetch_all(db_path, "SELECT relation FROM relation_clusters ORDER BY relation")
    relations = {r["relation"] for r in rows}
    expected = {
        "is_role",
        "works_at",
        "located_in",
        "prefers_language",
        "speaks_language",
        "has_skill",
        "works_on_project",
        "prefers_tool",
        "interested_in",
    }
    assert expected <= relations


def test_user_version_increments(tmp_path: Path) -> None:
    _, db_path = _open_migrated(tmp_path)
    version = _user_version(db_path)
    # AGENT_STATE_MIGRATIONS[-1][0] is the last version number
    assert version == AGENT_STATE_MIGRATIONS[-1][0]


def test_idempotent_remigration(tmp_path: Path) -> None:
    db, db_path = _open_migrated(tmp_path)
    # Running migrate again on an already-migrated DB must not raise
    migrate(db, AGENT_STATE_MIGRATIONS)
    assert "memory_items" in _tables(db_path)


def _legacy_pre_rename_migrations() -> list[tuple[int, str]]:
    """Reconstruct the migration list as the *pre-rename* binary stamped it.

    The pre-rename binary numbered ``mcp_user_tokens`` as v50 and never had the
    facts→memory_items rename steps.  We rebuild that exact list by dropping the
    two rename steps (identified by their SQL bodies) — plus any migrations appended
    *after* them (e.g. the mcp-per-user-apikey ``credential_kind`` column), which the
    v50-era binary never had — and renumbering the remainder contiguously, so applying
    it reproduces a real production DB left at ``user_version = 50`` with a populated
    ``facts`` table and the legacy free-text ``memory_items`` table still present.
    """
    kept = [
        sql
        for _v, sql in AGENT_STATE_MIGRATIONS
        if "INSERT INTO memory_items SELECT" not in sql
        and "fact_edges_new" not in sql
        and "ADD COLUMN credential_kind" not in sql
        # cron-durable-poll-engine appended the run-history table/index after the
        # rename; the v50-era binary never had them either.
        and "scheduled_task_runs" not in sql
        # add-workflow-engine appended the workflow run/step tables + indexes after the
        # rename; the v50-era binary never had them either.
        and "workflow_runs" not in sql
        and "workflow_step_runs" not in sql
    ]
    return [(i + 1, sql) for i, sql in enumerate(kept)]


def test_upgrade_from_legacy_v50_renames_facts_and_preserves_data(tmp_path: Path) -> None:
    """Regression: a DB stamped at the old v50 must still get facts renamed.

    The rename step must sit at a version *above* the highest version any live
    DB was ever stamped with (v50 = ``mcp_user_tokens`` in the pre-rename
    binary).  If it collides at v50 the migrate loop skips it (``50 <= 50``) and
    the rows are stranded in ``facts`` while the code reads ``memory_items``.
    """
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)

    legacy = _legacy_pre_rename_migrations()
    migrate(db, legacy)
    assert _user_version(db_path) == 50
    assert "facts" in _tables(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO facts (fact_id, user_id, subject, relation, object, cardinality, "
        "status, access_count, created_at, updated_at, statement, scope) VALUES "
        "('f1', 'u1', 'user', 'name', 'victor', 'single', 'active', 0, "
        "'2026-06-27T00:00:00', '2026-06-27T00:00:00', '用户的名字是 victor', 'situational')"
    )
    conn.commit()
    conn.close()

    migrate(db, AGENT_STATE_MIGRATIONS)

    assert _user_version(db_path) == AGENT_STATE_MIGRATIONS[-1][0]
    assert "facts" not in _tables(db_path)
    assert "memory_items" in _tables(db_path)
    rows = _fetch_all(db_path, "SELECT fact_id, subject, relation, object, scope FROM memory_items")
    assert len(rows) == 1
    assert tuple(rows[0]) == ("f1", "user", "name", "victor", "situational")
