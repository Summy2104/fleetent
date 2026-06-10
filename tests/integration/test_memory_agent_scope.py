"""Integration tests: memory/store.py connection comes from agent_scope (3b-3).

Verifies:
- memory/store.py has no create_database(...) self-connect to global DB
- memory/store.py has no ensure_schema-into-global residual
- connection is injected via set_state_db (called by agent boot wiring)
- after set_state_db, store operations write to the injected per-agent DB
- store raises RuntimeError before set_state_db is called
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


# ── Guard: no self-connection in memory/store.py ───────────────────────────


def test_memory_store_has_no_create_database_call() -> None:
    """memory/store.py must not call create_database() — connection is injected."""
    import fleetent.memory.store as module

    source = inspect.getsource(module)
    assert "create_database(" not in source, (
        "memory/store.py must not call create_database(); use injected set_state_db"
    )


def test_memory_store_has_no_ensure_schema_into_global() -> None:
    """ensure_schema must not create a global self-connection."""
    import fleetent.memory.store as module

    source = inspect.getsource(module)
    assert "Settings().database_url" not in source, (
        "memory/store.py must not resolve Settings().database_url — connection is injected"
    )


# ── set_state_db is exposed ────────────────────────────────────────────────


def test_memory_store_exposes_set_state_db() -> None:
    import fleetent.memory.store as module

    assert hasattr(module, "set_state_db"), "memory/store.py must expose set_state_db()"
    assert callable(module.set_state_db)


# ── Operations use injected DB ────────────────────────────────────────────


def test_memory_store_insert_uses_injected_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    import fleetent.memory.store as memory_store
    from fleetent.memory.models import MemoryItem

    db = _open_state_db(tmp_path)
    monkeypatch.setattr(memory_store, "_state_db", db)

    now = datetime.now(UTC).replace(microsecond=0)
    item = MemoryItem(
        id="test-id",
        user_id="alice",
        type="identity",
        content="User is an engineer",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    memory_store.insert_memory(item)

    row = db.execute(
        "SELECT id, user_id, content FROM memory_items WHERE id = :id", {"id": "test-id"}
    ).fetchone()
    assert row is not None
    assert row["user_id"] == "alice"
    assert row["content"] == "User is an engineer"


def test_memory_store_raises_when_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.memory.store as memory_store

    monkeypatch.setattr(memory_store, "_state_db", None)
    with pytest.raises(RuntimeError, match="set_state_db"):
        memory_store.memory_snapshot("alice")
