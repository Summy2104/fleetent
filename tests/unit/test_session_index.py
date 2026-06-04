import pytest

import fleetent.session_index as session_index


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_index, "DB_PATH", tmp_path / "x.db")


# --- 2. table / schema ---


def test_init_creates_sessions_table_with_expected_columns():
    session_index._init_db()
    import sqlite3

    with sqlite3.connect(session_index.DB_PATH) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert cols == {
        "session_id",
        "user_id",
        "created_at",
        "updated_at",
        "message_count",
        "agent_name",
    }


# --- 3. record_activity: first insert ---


def test_record_activity_first_insert(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 1000.0)
    session_index.record_activity("s1", user_id="u1", message_count=3, agent_name="bot")
    row = session_index.get("s1")
    assert row is not None
    assert row["session_id"] == "s1"
    assert row["user_id"] == "u1"
    assert row["message_count"] == 3
    assert row["agent_name"] == "bot"
    assert row["created_at"] == 1000.0
    assert row["updated_at"] == 1000.0


# --- 4. upsert update semantics ---


def test_record_activity_upsert_keeps_created_refreshes_updated(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 1000.0)
    session_index.record_activity("s1", user_id="u1", message_count=2, agent_name="bot")
    monkeypatch.setattr(session_index.time, "time", lambda: 2000.0)
    session_index.record_activity("s1", user_id="u2", message_count=5, agent_name="bot2")
    row = session_index.get("s1")
    assert row is not None
    assert row["created_at"] == 1000.0
    assert row["updated_at"] == 2000.0
    assert row["message_count"] == 5
    assert row["user_id"] == "u2"
    assert row["agent_name"] == "bot2"


# --- 5. query functions ---


def test_get_nonexistent_returns_none():
    session_index._init_db()
    assert session_index.get("missing") is None


def test_list_by_user_orders_by_updated_at_desc(monkeypatch):
    monkeypatch.setattr(session_index.time, "time", lambda: 100.0)
    session_index.record_activity("s1", user_id="u1", message_count=1, agent_name=None)
    monkeypatch.setattr(session_index.time, "time", lambda: 300.0)
    session_index.record_activity("s2", user_id="u1", message_count=1, agent_name=None)
    monkeypatch.setattr(session_index.time, "time", lambda: 200.0)
    session_index.record_activity("s3", user_id="u1", message_count=1, agent_name=None)
    session_index.record_activity("other", user_id="u2", message_count=1, agent_name=None)

    rows = session_index.list_by_user("u1")
    assert [r["session_id"] for r in rows] == ["s2", "s3", "s1"]


# --- 6. system-wide stats ---


def test_count_and_total_message_count():
    session_index.record_activity("s1", user_id="u1", message_count=2, agent_name=None)
    session_index.record_activity("s2", user_id="u1", message_count=3, agent_name=None)
    session_index.record_activity("s3", user_id="u2", message_count=5, agent_name=None)
    assert session_index.count() == 3
    assert session_index.total_message_count() == 10


def test_total_message_count_empty_is_zero():
    session_index._init_db()
    assert session_index.total_message_count() == 0
    assert session_index.count() == 0
