from __future__ import annotations

import json
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate


def _migrated(tmp_path: Path) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _columns(db: SQLiteDatabase, table: str) -> set[str]:
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def test_agent_state_migration_creates_im_outbound_queue(tmp_path: Path) -> None:
    db = _migrated(tmp_path)

    assert _columns(db, "im_outbound_queue") == {
        "id",
        "platform",
        "address_json",
        "payload_json",
        "dedup_key",
        "status",
        "attempts",
        "created_at",
        "sent_at",
    }


def test_im_outbound_queue_store_round_trip(tmp_path: Path) -> None:
    import fleetent.im_gateway.outbound_queue_store as store

    db = _migrated(tmp_path)
    store.set_state_db(db)

    queued = store.enqueue(
        platform="slack",
        address={"target": "U_APPROVER", "target_type": "user"},
        payload={"kind": "text", "text": "approval needed"},
        dedup_key="approval:a1:slack:U_APPROVER",
        created_at="2026-06-22T00:00:00+00:00",
    )

    pending = store.list_pending()
    assert [row["id"] for row in pending] == [queued["id"]]
    assert pending[0]["platform"] == "slack"
    assert json.loads(str(pending[0]["address_json"])) == {
        "target": "U_APPROVER",
        "target_type": "user",
    }
    assert json.loads(str(pending[0]["payload_json"])) == {
        "kind": "text",
        "text": "approval needed",
    }
    assert pending[0]["status"] == "pending"
    assert pending[0]["attempts"] == 0
    assert pending[0]["sent_at"] is None

    store.mark_failed(queued["id"])
    retried = store.list_pending()
    assert len(retried) == 1
    assert retried[0]["attempts"] == 1
    assert retried[0]["status"] == "pending"

    store.mark_sent(queued["id"], sent_at="2026-06-22T00:01:00+00:00")
    assert store.list_pending() == []

    sent = db.execute(
        "SELECT status, attempts, sent_at FROM im_outbound_queue WHERE id = :id",
        {"id": queued["id"]},
    ).fetchone()
    assert sent is not None
    assert dict(sent) == {
        "status": "sent",
        "attempts": 1,
        "sent_at": "2026-06-22T00:01:00+00:00",
    }
