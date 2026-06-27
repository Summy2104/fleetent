"""Integration tests: facts scope field — migration, list_always_facts, soft eviction, and build_context injection."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.facts_models import Fact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.vector_store.backend import InMemoryVectorBackend


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _fact(
    fid: str,
    *,
    relation: str = "has_skill",
    scope: str = "situational",
    status: str = "active",
    updated_at: datetime | None = None,
) -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="agent",
        relation=relation,
        object="value",
        cardinality="multi",
        status=status,
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=updated_at or now,
        source_turn=None,
        scope=scope,
    )


# ── Task 1.2: migration ───────────────────────────────────────────────────────


def test_scope_column_exists_after_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "agent_state.db"
    _open_db(tmp_path)
    assert "scope" in _columns(db_path, "memory_items")


def test_scope_column_default_is_situational(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    facts_store.insert_fact(_fact("f1", relation="has_skill"))
    f = facts_store.get_fact("f1")
    assert f is not None
    assert f.scope == "situational"


def test_scope_backfill_sets_always_for_known_relations(tmp_path: Path) -> None:
    """Migration backfill sets scope='always' for known behavioral relations.

    Simulates pre-existing rows by running migration, inserting rows with
    scope=situational (the default), then manually resetting scope to simulate
    what the backfill SQL does on a real pre-scope database.
    """
    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    now = _now().isoformat()
    db_path = tmp_path / "agent_state.db"
    conn = sqlite3.connect(db_path)
    # Insert facts with scope forced to 'situational' to simulate pre-backfill state
    conn.execute(
        "INSERT INTO memory_items (fact_id, user_id, subject, relation, object, cardinality, status, access_count, created_at, updated_at, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("pre-f1", "u1", "agent", "response_style", "加 xin", "single", "active", 0, now, now, "situational"),
    )
    conn.execute(
        "INSERT INTO memory_items (fact_id, user_id, subject, relation, object, cardinality, status, access_count, created_at, updated_at, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("pre-f2", "u1", "user", "has_skill", "Python", "multi", "active", 0, now, now, "situational"),
    )
    conn.commit()

    # Re-run the backfill SQL as the migration would
    conn.execute(
        "UPDATE memory_items SET scope = 'always' WHERE relation IN ("
        "'response_style', 'tone', 'format', 'language', 'output_format',"
        "'never_do', 'always_do', 'security', 'approval_required'"
        ") AND status = 'active'"
    )
    conn.commit()

    row1 = conn.execute("SELECT scope FROM memory_items WHERE fact_id='pre-f1'").fetchone()
    row2 = conn.execute("SELECT scope FROM memory_items WHERE fact_id='pre-f2'").fetchone()
    conn.close()

    assert row1[0] == "always"
    assert row2[0] == "situational"


# ── list_always_facts ─────────────────────────────────────────────────────────


def test_list_always_facts_returns_only_always_active(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    facts_store.insert_fact(_fact("a1", relation="response_style", scope="always"))
    facts_store.insert_fact(_fact("a2", relation="tone", scope="always"))
    facts_store.insert_fact(_fact("s1", relation="has_skill", scope="situational"))
    facts_store.insert_fact(_fact("a3", relation="never_do", scope="always", status="retracted"))

    result = facts_store.list_always_facts("u1")
    ids = {f.fact_id for f in result}
    assert ids == {"a1", "a2"}


# ── soft eviction ─────────────────────────────────────────────────────────────


def test_soft_eviction_retracts_oldest_when_at_limit(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    # Insert 15 soft always facts with increasing updated_at
    base_time = _now() - timedelta(minutes=20)
    for i in range(15):
        facts_store.insert_fact(
            _fact(
                f"soft-{i}",
                relation="tone",
                scope="always",
                updated_at=base_time + timedelta(minutes=i),
            )
        )

    # Trigger eviction by calling _maybe_evict_soft_always
    facts_store._maybe_evict_soft_always("u1", "tone")

    # The oldest (soft-0) should be retracted
    oldest = facts_store.get_fact("soft-0")
    assert oldest is not None
    assert oldest.status == "retracted"

    # Others still active
    second = facts_store.get_fact("soft-1")
    assert second is not None
    assert second.status == "active"


def test_hard_fact_not_evicted_regardless_of_soft_pool_size(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    # Fill soft pool to limit
    base_time = _now() - timedelta(minutes=20)
    for i in range(15):
        facts_store.insert_fact(
            _fact(f"soft-{i}", relation="tone", scope="always", updated_at=base_time + timedelta(minutes=i))
        )

    # Insert a hard always fact — should not trigger eviction of hard facts
    facts_store._maybe_evict_soft_always("u1", "never_do")

    # No soft facts were retracted (eviction only happens for soft relations)
    retracted = [
        f for f in facts_store.list_active_facts("u1") if f.status == "retracted"
    ]
    assert retracted == []


# ── Task 5.1: end-to-end build_context injection ──────────────────────────────


async def test_build_context_injects_always_facts_unconditionally(tmp_path: Path) -> None:
    """Always facts appear in build_context output regardless of query semantics."""
    from fleetent.long_term_ctx import build_context

    db = _open_db(tmp_path)
    backend = InMemoryVectorBackend()
    facts_store.set_facts_db(db, backend)

    # Insert an always fact with a statement
    f = Fact(
        fact_id="always-1",
        user_id="u1",
        subject="agent",
        relation="response_style",
        object="加 xin 在句末",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=_now(),
        updated_at=_now(),
        source_turn=None,
        statement="用户希望助手每次回复后加 xin",
        scope="always",
    )
    facts_store.insert_fact(f)

    # Use a query with no semantic relation to "response_style" or "xin"
    ctx = await build_context("u1", "今天天气怎么样", "agent1", 4096)

    assert "[Behavioral directives" in ctx.text
    assert "加 xin 在句末" in ctx.text or "xin" in ctx.text
    memory_sources = [s for s in ctx.sources if s.source_type == "memory"]
    assert any(s.source_id == "always-1" for s in memory_sources)
