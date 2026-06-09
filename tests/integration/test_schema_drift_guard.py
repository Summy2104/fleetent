"""Schema drift guard: alembic head vs ensure_schema column consistency.

Two independent schema creation paths exist:
  A – alembic upgrade head (management / platform path)
  B – each store's ensure_schema() (agent self-init path)

For every agent-side table created by ensure_schema(), its column set MUST equal the
column set produced by alembic for the same table. This test enforces that invariant
so the two schema authorities never quietly diverge.

Teeth are verified by test_drift_guard_detects_column_mismatch: if we alter the guard
comparison to include a phantom column the guard turns red, proving the check has bite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.integration._migration_template import apply_migrations


def _cols(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    conn.close()
    return {r[1] for r in rows}


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def _build_alembic_db(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "alembic_head.db"
    apply_migrations(db)
    return db


def _build_ensure_schema_db(tmp_path: Path) -> Path:
    """Run all agent-side ensure_schema() functions on a fresh DB."""
    from fleetent.db import SQLiteDatabase
    from fleetent.knowledge_base import operations as kb_ops
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces
    from fleetent.reflection import ensure_schema as reflection_ensure_schema
    from fleetent.session import index as session_index

    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "ensure_schema.db"
    db = SQLiteDatabase(path=db_path)
    traces.ensure_schema(db)
    memory_store.ensure_schema(db)
    reflection_ensure_schema(db)
    kb_ops.ensure_schema(db)
    session_index.ensure_schema(db)  # session.index.ensure_schema added in task 3.2
    return db_path


def _build_ensure_schema_db_without_session(tmp_path: Path) -> Path:
    """Run ensure_schema() for all stores except session.index (which is pending task 3.2)."""
    from fleetent.db import SQLiteDatabase
    from fleetent.knowledge_base import operations as kb_ops
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces
    from fleetent.reflection import ensure_schema as reflection_ensure_schema

    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "ensure_schema.db"
    db = SQLiteDatabase(path=db_path)
    traces.ensure_schema(db)
    memory_store.ensure_schema(db)
    reflection_ensure_schema(db)
    kb_ops.ensure_schema(db)
    return db_path


def test_no_drift_between_alembic_head_and_ensure_schema(tmp_path: Path) -> None:
    """For every agent-side table that also appears in alembic, column sets must match.

    Tables present only in ensure_schema (e.g. `sessions`) are pure agent-side tables
    with no alembic counterpart — they are skipped by this guard.
    """
    alembic_db = _build_alembic_db(tmp_path / "a")
    ensure_db = _build_ensure_schema_db(tmp_path / "b")

    alembic_tables = _table_names(alembic_db)
    ensure_tables = _table_names(ensure_db)

    drifted: list[str] = []
    for table in ensure_tables:
        if table.startswith("knowledge_chunks_fts"):
            # FTS5 virtual tables expose synthetic columns; skip structural comparison.
            continue
        if table not in alembic_tables:
            # Pure agent-side table (no alembic counterpart); nothing to compare against.
            continue
        alembic_cols = _cols(alembic_db, table)
        ensure_cols = _cols(ensure_db, table)
        if alembic_cols != ensure_cols:
            missing = alembic_cols - ensure_cols
            extra = ensure_cols - alembic_cols
            drifted.append(f"{table}: missing={missing!r} extra={extra!r}")

    assert not drifted, "Schema drift detected:\n" + "\n".join(f"  {d}" for d in drifted)


def test_drift_guard_detects_column_mismatch(tmp_path: Path) -> None:
    """Teeth: the guard catches a deliberate extra column in ensure_schema DDL."""
    from fleetent.db import SQLiteDatabase

    alembic_db = _build_alembic_db(tmp_path / "alembic_teeth")

    # Distorted DB: traces table with an extra phantom column.
    distorted_db_path = tmp_path / "distorted.db"
    distorted = SQLiteDatabase(path=distorted_db_path)
    distorted.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            id              TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL,
            span_id         TEXT,
            parent_span_id  TEXT,
            session_id      TEXT,
            user_id         TEXT,
            agent_id        TEXT,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            event_type      TEXT NOT NULL,
            ts              TEXT NOT NULL,
            payload_json    TEXT NOT NULL,
            phantom_col     TEXT            -- deliberate extra column
        )
        """
    )

    alembic_cols = _cols(alembic_db, "traces")
    distorted_cols = _cols(distorted_db_path, "traces")
    assert alembic_cols != distorted_cols, (
        "Guard has no teeth: distorted schema was not detected as different"
    )
