"""Integration tests: archive_expired_facts lifecycle job."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.facts_models import Fact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _fact(fid: str, *, expires_at, last_accessed_at, created_at=None) -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation="has_skill",
        object="Python",
        cardinality="multi",
        status="active",
        access_count=1,
        first_accessed_at=last_accessed_at,
        last_accessed_at=last_accessed_at,
        expires_at=expires_at,
        valid_until=None,
        created_at=created_at or now,
        updated_at=now,
        source_turn=None,
    )


async def test_archive_expired_at(tmp_path: Path) -> None:
    from fleetent.memory import facts_lifecycle

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    facts_store.insert_fact(
        _fact("expired", expires_at=now - timedelta(days=1), last_accessed_at=now)
    )

    await facts_lifecycle.archive_expired_facts(db, None, now=now)

    f = facts_store.get_fact("expired")
    assert f is not None and f.status == "archived"


async def test_archive_idle_30_days(tmp_path: Path) -> None:
    from fleetent.memory import facts_lifecycle

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    # expires_at in the future, but last_accessed_at 35 days ago.
    facts_store.insert_fact(
        _fact(
            "idle",
            expires_at=now + timedelta(days=10),
            last_accessed_at=now - timedelta(days=35),
        )
    )

    await facts_lifecycle.archive_expired_facts(db, None, now=now)

    f = facts_store.get_fact("idle")
    assert f is not None and f.status == "archived"


async def test_long_term_unaffected(tmp_path: Path) -> None:
    from fleetent.memory import facts_lifecycle

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    facts_store.insert_fact(
        _fact("longterm", expires_at=None, last_accessed_at=now - timedelta(days=100))
    )

    await facts_lifecycle.archive_expired_facts(db, None, now=now)

    f = facts_store.get_fact("longterm")
    assert f is not None and f.status == "active"
