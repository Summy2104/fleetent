import pytest

import fleetent.session.index as session_index
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as SESSION_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    # Inject a fresh per-agent state DB for each test, mirroring how agent boot wires
    # session.index via agent_scope + migrate-on-open (3b-1).
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, SESSION_MIGRATIONS)
    monkeypatch.setattr(session_index, "_state_db", db)
    return db.path


# --- 2. table / schema ---


def test_init_creates_sessions_table_with_expected_columns(_isolate_db):
    import sqlite3

    with sqlite3.connect(_isolate_db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert cols == {
        "session_id",
        "user_id",
        "created_at",
        "updated_at",
        "message_count",
    }


# --- 3. record_activity: first insert ---


def test_record_activity_first_insert(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 1000.0)
    session_index.record_activity("s1", user_id="u1", message_count=3)
    row = session_index.get("s1")
    assert row is not None
    assert row["session_id"] == "s1"
    assert row["user_id"] == "u1"
    assert row["message_count"] == 3
    assert row["created_at"] == 1000.0
    assert row["updated_at"] == 1000.0


# --- 4. upsert update semantics ---


def test_record_activity_upsert_keeps_created_refreshes_updated(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 1000.0)
    session_index.record_activity("s1", user_id="u1", message_count=2)
    monkeypatch.setattr(session_index.time, "time", lambda: 2000.0)
    session_index.record_activity("s1", user_id="u2", message_count=5)
    row = session_index.get("s1")
    assert row is not None
    assert row["created_at"] == 1000.0
    assert row["updated_at"] == 2000.0
    assert row["message_count"] == 5
    assert row["user_id"] == "u2"


# --- 5. query functions ---


def test_get_nonexistent_returns_none():
    assert session_index.get("missing") is None


def test_list_by_user_orders_by_updated_at_desc(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 100.0)
    session_index.record_activity("s1", user_id="u1", message_count=1)
    monkeypatch.setattr(session_index.time, "time", lambda: 300.0)
    session_index.record_activity("s2", user_id="u1", message_count=1)
    monkeypatch.setattr(session_index.time, "time", lambda: 200.0)
    session_index.record_activity("s3", user_id="u1", message_count=1)
    session_index.record_activity("other", user_id="u2", message_count=1)

    rows = session_index.list_by_user("u1")
    assert [r["session_id"] for r in rows] == ["s2", "s3", "s1"]


# --- 6. system-wide stats ---


def test_count_and_total_message_count():
    session_index.record_activity("s1", user_id="u1", message_count=2)
    session_index.record_activity("s2", user_id="u1", message_count=3)
    session_index.record_activity("s3", user_id="u2", message_count=5)
    assert session_index.count() == 3
    assert session_index.total_message_count() == 10


def test_total_message_count_empty_is_zero():
    assert session_index.total_message_count() == 0
    assert session_index.count() == 0


# --- 7. delete / delete_batch ---


def test_delete_removes_existing_row():
    session_index.record_activity("del-s1", user_id="u1", message_count=1)
    assert session_index.get("del-s1") is not None
    session_index.delete("del-s1")
    assert session_index.get("del-s1") is None


def test_delete_nonexistent_is_idempotent():
    # Should not raise
    session_index.delete("no-such-session")


def test_delete_batch_removes_multiple_rows():
    session_index.record_activity("b1", user_id="u1", message_count=1)
    session_index.record_activity("b2", user_id="u1", message_count=1)
    session_index.record_activity("b3", user_id="u1", message_count=1)
    session_index.delete_batch(["b1", "b2"])
    assert session_index.get("b1") is None
    assert session_index.get("b2") is None
    assert session_index.get("b3") is not None  # unaffected


def test_delete_batch_empty_list_is_idempotent():
    # Should not raise
    session_index.delete_batch([])


def test_delete_reduces_count():
    session_index.record_activity("c1", user_id="u1", message_count=1)
    session_index.record_activity("c2", user_id="u1", message_count=1)
    before = session_index.count()
    session_index.delete("c1")
    assert session_index.count() == before - 1


# --- 8. list_by_user pagination ---


def test_list_by_user_limit_truncates_results(monkeypatch):
    t = 100.0
    for i in range(5):
        monkeypatch.setattr(session_index.time, "time", lambda _t=t + i: _t)
        session_index.record_activity(f"pg-{i}", user_id="pguser", message_count=1)

    rows = session_index.list_by_user("pguser", limit=2)
    assert len(rows) == 2


def test_list_by_user_cursor_before_updated_at(monkeypatch):
    for ts, sid in [(100.0, "pg-a"), (200.0, "pg-b"), (300.0, "pg-c")]:
        monkeypatch.setattr(session_index.time, "time", lambda _t=ts: _t)
        session_index.record_activity(sid, user_id="pguser2", message_count=1)

    # Cursor at 250 → only pg-a (100) and pg-b (200) qualify
    rows = session_index.list_by_user("pguser2", before_updated_at=250.0)
    assert {r["session_id"] for r in rows} == {"pg-a", "pg-b"}


def test_list_by_user_default_limit_is_50(monkeypatch):
    """Default limit=50 means at most 50 rows returned."""
    for i in range(60):
        monkeypatch.setattr(session_index.time, "time", lambda _i=i: float(_i))
        session_index.record_activity(f"many-{i}", user_id="biguser", message_count=1)

    rows = session_index.list_by_user("biguser")
    assert len(rows) == 50


def test_list_by_user_cursor_and_limit_combined(monkeypatch):
    for ts, sid in [(10.0, "x1"), (20.0, "x2"), (30.0, "x3"), (40.0, "x4")]:
        monkeypatch.setattr(session_index.time, "time", lambda _t=ts: _t)
        session_index.record_activity(sid, user_id="curuser", message_count=1)

    # before_updated_at=35 → x1(10), x2(20), x3(30); limit=2 → x3, x2 (desc)
    rows = session_index.list_by_user("curuser", limit=2, before_updated_at=35.0)
    assert [r["session_id"] for r in rows] == ["x3", "x2"]
