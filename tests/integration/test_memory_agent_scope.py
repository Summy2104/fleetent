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
from fleetent.vector_store.backend import SearchResult


def _open_state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


class _TrackingBackend:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[float], str]] = []
        self.deletes: list[tuple[str, str]] = []
        self.searches: list[tuple[list[float], str, int]] = []
        self._results: list[SearchResult] = []

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self.upserts.append((id, vector, namespace))

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        self.searches.append((vector, namespace, limit))
        return list(self._results)

    async def delete(self, id: str, namespace: str) -> None:
        self.deletes.append((id, namespace))

    async def clear_namespace(self, namespace: str) -> None:
        return None


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


def test_memory_store_insert_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_memory_store_exposes_set_vector_backend() -> None:
    import fleetent.memory.store as memory_store

    assert hasattr(memory_store, "set_vector_backend")
    assert callable(memory_store.set_vector_backend)


async def test_memory_store_uses_injected_vector_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.memory.store as memory_store

    backend = _TrackingBackend()
    monkeypatch.setattr(memory_store, "_vector_backend", backend, raising=False)

    await memory_store.vector_backend().upsert("mem-1", [0.1, 0.2], "mem:alice")
    results = await memory_store.vector_backend().search([0.1, 0.2], "mem:alice", limit=3)
    await memory_store.vector_backend().delete("mem-1", "mem:alice")

    assert backend.upserts == [("mem-1", [0.1, 0.2], "mem:alice")]
    assert backend.searches == [([0.1, 0.2], "mem:alice", 3)]
    assert backend.deletes == [("mem-1", "mem:alice")]
    assert results == []


def test_memory_store_vector_backend_raises_when_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.memory.store as memory_store

    monkeypatch.setattr(memory_store, "_vector_backend", None, raising=False)
    with pytest.raises(RuntimeError, match="set_vector_backend"):
        memory_store.vector_backend()
