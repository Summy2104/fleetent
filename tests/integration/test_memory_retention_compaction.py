import sqlite3

from fleetent.db import SQLiteDatabase
from fleetent.memory import maintenance, store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-retention.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(store, "_state_db", db)
    return db_path


class _TrackingBackend:
    def __init__(self) -> None:
        self.deletes: list[tuple[str, str]] = []

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        return None

    async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[object]:
        return []

    async def delete(self, id: str, namespace: str) -> None:
        self.deletes.append((id, namespace))

    async def clear_namespace(self, namespace: str) -> None:
        return None


def _insert_memory(
    db_path,
    *,
    id: str,
    user_id: str = "user-1",
    type: str = "identity",
    content: str = "User likes Python",
    updated_at: str = "2026-01-01T00:00:00+00:00",
    expires_at: str | None = None,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, updated_at, updated_at, expires_at),
        )


def _memory_ids(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM memory_items ORDER BY id")]


async def test_apply_deletes_expired_context_rows_and_vectors(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="ctx-expired",
        type="context",
        content="User is working on old billing migration",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="identity-current",
        type="identity",
        content="User is a platform engineer",
    )
    backend = _TrackingBackend()
    vector_delete = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_delete.append((id, namespace))

    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(),
        dry_run=False,
    )

    assert summary.expired_count == 1
    assert summary.deleted_ids == ["ctx-expired"]
    assert _memory_ids(db_path) == ["identity-current"]
    assert backend.deletes == [("ctx-expired", "mem:user-1")]
    assert vector_delete == []


async def test_apply_deletes_older_over_limit_rows_and_vectors(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="pref-new",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="pref-old",
        type="preferences",
        content="User prefers verbose answers",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    backend = _TrackingBackend()
    vector_delete = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_delete.append((id, namespace))

    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(max_preferences=1),
        dry_run=False,
    )

    assert summary.over_limit_count == 1
    assert summary.deleted_ids == ["pref-old"]
    assert _memory_ids(db_path) == ["pref-new"]
    assert backend.deletes == [("pref-old", "mem:user-1")]
    assert vector_delete == []


async def test_apply_duplicate_compaction_removes_duplicates_but_keeps_canonical(
    tmp_path, monkeypatch
):
    from fleetent import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="pref-canonical",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="pref-duplicate",
        type="preferences",
        content="user prefers concise answers",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    backend = _TrackingBackend()
    vector_delete = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_delete.append((id, namespace))

    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(compact_duplicates=True),
        dry_run=False,
    )

    assert summary.compacted_count == 1
    assert summary.deleted_ids == ["pref-duplicate"]
    assert _memory_ids(db_path) == ["pref-canonical"]
    assert backend.deletes == [("pref-duplicate", "mem:user-1")]
    assert vector_delete == []


async def test_apply_is_scoped_to_requested_user_and_vector_namespace(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="user-a-expired",
        user_id="user-a",
        type="context",
        content="User A old project",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="user-b-expired",
        user_id="user-b",
        type="context",
        content="User B old project",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    backend = _TrackingBackend()
    vector_delete = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_delete.append((id, namespace))

    monkeypatch.setattr(store, "_vector_backend", backend, raising=False)
    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-a",
        policy=memory_layer.MemoryMaintenancePolicy(),
        dry_run=False,
    )

    assert summary.deleted_ids == ["user-a-expired"]
    assert _memory_ids(db_path) == ["user-b-expired"]
    assert backend.deletes == [("user-a-expired", "mem:user-a")]
    assert vector_delete == []
