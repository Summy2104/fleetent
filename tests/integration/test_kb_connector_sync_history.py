"""Integration tests: knowledge_connector_sync_history appends + list API."""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


def _build_kb_db(tmp_path: Path) -> SQLiteDatabase:
    db_path = tmp_path / "kb.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, KB_MIGRATIONS)
    return db


def test_record_connector_status_appends_history_row(tmp_path: Path) -> None:
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    operations.record_connector_status(
        connector_id="conn-1",
        connector_type="google_drive",
        tenant_id="t1",
        kb_id="kb1",
        status="sync_ok",
        summary={"added": 3},
        error=None,
        database=db,
    )
    rows = operations.list_connector_sync_history("conn-1", limit=10, database=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["connector_id"] == "conn-1"
    assert row["status"] == "sync_ok"
    assert row["error"] is None


def test_list_connector_sync_history_descending_order(tmp_path: Path) -> None:
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    for i in range(3):
        operations.record_connector_status(
            connector_id="conn-2",
            connector_type="google_drive",
            tenant_id="t1",
            kb_id="kb1",
            status=f"sync_{i}",
            summary={},
            error=None,
            database=db,
        )
    rows = operations.list_connector_sync_history("conn-2", limit=10, database=db)
    assert len(rows) == 3
    statuses = [r["status"] for r in rows]
    assert statuses == ["sync_2", "sync_1", "sync_0"]


def test_list_connector_sync_history_limit(tmp_path: Path) -> None:
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    for i in range(5):
        operations.record_connector_status(
            connector_id="conn-3",
            connector_type="google_drive",
            tenant_id="t1",
            kb_id="kb1",
            status=f"run_{i}",
            summary={},
            error=None,
            database=db,
        )
    rows = operations.list_connector_sync_history("conn-3", limit=2, database=db)
    assert len(rows) == 2


def test_history_records_error_field(tmp_path: Path) -> None:
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    operations.record_connector_status(
        connector_id="conn-4",
        connector_type="confluence",
        tenant_id="t1",
        kb_id="kb1",
        status="sync_failed",
        summary={},
        error="auth expired",
        database=db,
    )
    rows = operations.list_connector_sync_history("conn-4", limit=1, database=db)
    assert rows[0]["error"] == "auth expired"


def test_history_isolated_by_connector_id(tmp_path: Path) -> None:
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    operations.record_connector_status(
        connector_id="conn-a",
        connector_type="google_drive",
        tenant_id="t1",
        kb_id="kb1",
        status="ok",
        summary={},
        error=None,
        database=db,
    )
    operations.record_connector_status(
        connector_id="conn-b",
        connector_type="confluence",
        tenant_id="t1",
        kb_id="kb1",
        status="ok",
        summary={},
        error=None,
        database=db,
    )
    assert len(operations.list_connector_sync_history("conn-a", limit=10, database=db)) == 1
    assert len(operations.list_connector_sync_history("conn-b", limit=10, database=db)) == 1


def test_last_row_status_still_updated(tmp_path: Path) -> None:
    """knowledge_connector_status last-row table must still be updated alongside history."""
    from fleetent.knowledge_base import operations

    db = _build_kb_db(tmp_path)
    operations.record_connector_status(
        connector_id="conn-5",
        connector_type="google_drive",
        tenant_id="t1",
        kb_id="kb1",
        status="sync_ok",
        summary={"added": 5},
        error=None,
        database=db,
    )
    row = db.execute(
        "SELECT last_status FROM knowledge_connector_status WHERE connector_id = :id",
        {"id": "conn-5"},
    ).fetchone()
    assert row is not None
    assert row["last_status"] == "sync_ok"
