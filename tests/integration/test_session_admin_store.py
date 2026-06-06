"""Tests for session_admin_store (migration 014) + session_mgr clear/inject hooks."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.chat_management import session_admin_store as store
from fleetent.session import manager as session_mgr


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


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


def test_upsert_playground_origin(store_db):
    store.upsert_meta("s1", origin="playground", agent_name="ops")
    assert store.get_meta("s1")["origin"] == "playground"


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


# --- migration 054: session_meta compaction columns ---


def test_migration_054_adds_compaction_columns(tmp_path):
    """Migration 054 adds four compaction-related columns to session_meta."""
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()}
    conn.close()
    assert "last_compaction_at" in cols
    assert "messages_before_compaction" in cols
    assert "messages_after_compaction" in cols
    assert "compaction_summary_preview" in cols


def test_migration_054_compaction_columns_are_nullable_for_existing_rows(tmp_path, monkeypatch):
    """Existing session_meta rows have NULL in new compaction columns after migration."""
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("s1", origin="web")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT last_compaction_at, messages_before_compaction"
        " FROM session_meta WHERE session_id = ?",
        ("s1",),
    ).fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None


# --- update_compaction_meta ---


def test_update_compaction_meta_sets_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("sess-c", origin="web")

    store.update_compaction_meta(
        "sess-c",
        messages_before=50,
        messages_after=12,
        summary_preview="This is the summary",
        compacted_at=1234567890.0,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT last_compaction_at, messages_before_compaction, messages_after_compaction, "
        "compaction_summary_preview FROM session_meta WHERE session_id = ?",
        ("sess-c",),
    ).fetchone()
    conn.close()
    assert row[0] == 1234567890.0
    assert row[1] == 50
    assert row[2] == 12
    assert row[3] == "This is the summary"


def test_update_compaction_meta_truncates_preview_to_200_chars(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("sess-d", origin="web")

    long_preview = "x" * 500
    store.update_compaction_meta(
        "sess-d",
        messages_before=10,
        messages_after=3,
        summary_preview=long_preview,
        compacted_at=0.0,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT compaction_summary_preview FROM session_meta WHERE session_id = ?",
        ("sess-d",),
    ).fetchone()
    conn.close()
    assert len(row[0]) == 200


# --- migration 055: token columns ---


def test_migration_055_adds_token_columns(tmp_path):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()}
    conn.close()
    assert "total_input_tokens" in cols
    assert "total_output_tokens" in cols


def test_add_token_usage_accumulates(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.add_token_usage("tok-s", 100, 50)
    store.add_token_usage("tok-s", 100, 50)
    m = store.get_meta("tok-s")
    assert m["total_input_tokens"] == 200
    assert m["total_output_tokens"] == 100


def test_add_token_usage_creates_row_if_absent(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.add_token_usage("fresh-tok", 30, 20)
    m = store.get_meta("fresh-tok")
    assert m["total_input_tokens"] == 30
    assert m["total_output_tokens"] == 20


def test_get_meta_includes_token_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("meta-tok", origin="web")
    m = store.get_meta("meta-tok")
    assert "total_input_tokens" in m
    assert "total_output_tokens" in m


# --- migration 056: resume_pending ---


def test_migration_056_adds_resume_pending_column(tmp_path):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()}
    conn.close()
    assert "resume_pending" in cols


def test_mark_and_list_resume_pending(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.mark_resume_pending("rp1")
    assert "rp1" in store.list_resume_pending()


def test_clear_resume_pending(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.mark_resume_pending("rp2")
    store.clear_resume_pending("rp2")
    assert "rp2" not in store.list_resume_pending()


def test_mark_resume_pending_creates_row(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.mark_resume_pending("rp-fresh")
    assert store.get_meta("rp-fresh")["resume_pending"] == 1


def test_scan_and_mark_recent_marks_window(tmp_path, monkeypatch):

    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # recent session
    store.upsert_meta("recent", origin="web")
    marked = store.scan_and_mark_recent(window_seconds=120)
    assert "recent" in marked
    assert store.get_meta("recent")["resume_pending"] == 1


def test_scan_and_mark_recent_skips_old(tmp_path, monkeypatch):
    import datetime

    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("oldsess", origin="web")
    # Force updated_at far in the past
    old_iso = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE session_meta SET updated_at = ? WHERE session_id = ?", (old_iso, "oldsess")
    )
    conn.commit()
    conn.close()
    marked = store.scan_and_mark_recent(window_seconds=120)
    assert "oldsess" not in marked


def test_get_meta_includes_resume_pending(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    store.upsert_meta("rp-meta", origin="web")
    assert "resume_pending" in store.get_meta("rp-meta")
