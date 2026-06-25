"""Integration tests: the background archive sweep loop runs and is fault-isolated."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_lifecycle, facts_store
from fleetent.memory.facts_models import Fact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def test_sweep_loop_archives_then_can_be_stopped(tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    facts_store.insert_fact(
        Fact(
            fact_id="expired",
            user_id="u1",
            subject="user",
            relation="has_skill",
            object="Python",
            cardinality="multi",
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=now - timedelta(days=1),
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
        )
    )

    task = facts_lifecycle.start_archive_sweep(db, None, interval=0.05)
    try:
        # Give the loop a couple of ticks to run one sweep.
        await asyncio.sleep(0.2)
        f = facts_store.get_fact("expired")
        assert f is not None and f.status == "archived"
    finally:
        await facts_lifecycle.stop_archive_sweep()
    assert task.done()
