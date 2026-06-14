"""Tests for session_admin_store (migration 014) + session_mgr clear/inject hooks."""

import sqlite3

import pytest

from fleetent import agent_store
from fleetent.platform.chat_management import session_admin_store as store
from fleetent.session import manager as session_mgr
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_table(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "session_meta" in tables


def test_meta_defaults(store_db):
    m = store.get_meta("never")
    assert m["origin"] == "web"
    assert m["status"] == "active"
    assert m["takeover_actor"] is None
    assert m["pinned"] == 0
    assert m["agent_id"] is None
    assert m["agent_name"] is None


def test_upsert_playground_origin(store_db):
    agent_id = agent_store.create_agent("ops", "Ops.", ["shell"]).id
    store.upsert_meta("s1", origin="playground", agent_id=agent_id)
    assert store.get_meta("s1")["origin"] == "playground"
    assert store.get_meta("s1")["agent_id"] == agent_id
    assert store.get_meta("s1")["agent_name"] == "ops"


def test_status_transitions(store_db):
    store.set_status("s1", "ended")
    assert store.get_meta("s1")["status"] == "ended"
    with pytest.raises(ValueError):
        store.set_status("s1", "bogus")


def test_takeover_set_and_clear(store_db):
    store.set_takeover("s1", "admin-1")
    assert store.is_taken_over("s1") is True
    store.clear_takeover("s1")
    assert store.is_taken_over("s1") is False


def test_pin(store_db):
    store.set_pinned("s1", True, note="good demo")
    m = store.get_meta("s1")
    assert m["pinned"] == 1 and m["pin_note"] == "good demo"


def test_list_excludes_playground_by_default(store_db):
    store.upsert_meta("real", origin="web", user_id="u1")
    store.upsert_meta("play", origin="playground")
    ids = {m["session_id"] for m in store.list_meta()}
    assert "real" in ids and "play" not in ids
    allids = {m["session_id"] for m in store.list_meta(include_playground=True)}
    assert "play" in allids


def test_list_filter_by_user(store_db):
    store.upsert_meta("a", origin="web", user_id="u1")
    store.upsert_meta("b", origin="web", user_id="u2")
    assert {m["session_id"] for m in store.list_meta(user_id="u1")} == {"a"}


def test_list_filter_by_agent_id(store_db):
    ops = agent_store.create_agent("ops", "Ops.", ["shell"]).id
    support = agent_store.create_agent("support", "Support.", ["shell"]).id
    store.upsert_meta("a", origin="web", user_id="u1", agent_id=ops)
    store.upsert_meta("b", origin="web", user_id="u1", agent_id=support)
    assert {m["session_id"] for m in store.list_meta(agent_id=ops)} == {"a"}


# --- session_mgr hooks ---


async def test_clear_empties_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    await session_mgr.save("s1", [{"role": "user", "content": "hi"}])
    await session_mgr.clear("s1")
    assert await session_mgr.load("s1") == []


async def test_inject_appends_under_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    await session_mgr.save("s1", [{"role": "user", "content": "hi"}])
    await session_mgr.inject_message("s1", "human_agent", "let me help")
    msgs = await session_mgr.load("s1")
    assert msgs[-1] == {"role": "human_agent", "content": "let me help"}


# --- migration 058: drop runtime-coupling columns ---


def test_migration_058_drops_token_and_compaction_columns(tmp_path):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()}
    conn.close()
    for dropped in (
        "total_input_tokens",
        "total_output_tokens",
        "last_compaction_at",
        "messages_before_compaction",
        "messages_after_compaction",
        "compaction_summary_preview",
    ):
        assert dropped not in cols, f"{dropped} should have been dropped by migration 058"


def test_migration_059_drops_resume_pending_column(tmp_path):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()}
    conn.close()
    assert "resume_pending" not in cols  # dropped by migration 059
    # core governance columns remain
    assert {"session_id", "origin", "status", "pinned"} <= cols
