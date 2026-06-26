"""Integration tests: access update + auto-upgrade to long-term."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_search, facts_store
from fleetent.memory.facts_models import Fact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _short_term_fact(fid: str, *, access_count: int, first_accessed_at, expires_in_days=10) -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation="has_skill",
        object="Python",
        cardinality="multi",
        status="active",
        access_count=access_count,
        first_accessed_at=first_accessed_at,
        last_accessed_at=first_accessed_at,
        expires_at=now + timedelta(days=expires_in_days),
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )


def test_upgrade_when_access_and_age_met(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    # access_count already 9; first access 15 days ago. One more access -> 10, age 15d.
    facts_store.insert_fact(
        _short_term_fact("f1", access_count=9, first_accessed_at=now - timedelta(days=15))
    )

    facts_search._update_access(["f1"], now)

    updated = facts_store.get_fact("f1")
    assert updated is not None
    assert updated.access_count == 10
    assert updated.expires_at is None  # upgraded to long-term


def test_no_upgrade_when_age_insufficient(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    facts_store.insert_fact(
        _short_term_fact("f2", access_count=14, first_accessed_at=now - timedelta(days=5))
    )

    facts_search._update_access(["f2"], now)

    updated = facts_store.get_fact("f2")
    assert updated is not None
    assert updated.access_count == 15
    assert updated.expires_at is not None  # NOT upgraded (age < 14d)


def test_no_upgrade_when_access_insufficient(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    facts_store.insert_fact(
        _short_term_fact("f3", access_count=2, first_accessed_at=now - timedelta(days=20))
    )

    facts_search._update_access(["f3"], now)

    updated = facts_store.get_fact("f3")
    assert updated is not None
    assert updated.access_count == 3
    assert updated.expires_at is not None  # NOT upgraded (access < 10)
