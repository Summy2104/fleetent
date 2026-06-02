import sqlite3

from fleetent.intelligence.memory import maintenance
from tests.integration.test_migrations import apply_migrations


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-retention.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


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
    from fleetent import memory_layer

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
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(),
        dry_run=False,
    )

    assert summary.expired_count == 1
    assert summary.deleted_ids == ["ctx-expired"]
    assert _memory_ids(db_path) == ["identity-current"]
    assert vector_deletes == [("ctx-expired", "mem:user-1")]


async def test_apply_deletes_older_over_limit_rows_and_vectors(tmp_path, monkeypatch):
    from fleetent import memory_layer

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
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(max_preferences=1),
        dry_run=False,
    )

    assert summary.over_limit_count == 1
    assert summary.deleted_ids == ["pref-old"]
    assert _memory_ids(db_path) == ["pref-new"]
    assert vector_deletes == [("pref-old", "mem:user-1")]


async def test_apply_duplicate_compaction_removes_duplicates_but_keeps_canonical(
    tmp_path, monkeypatch
):
    from fleetent import memory_layer

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
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(compact_duplicates=True),
        dry_run=False,
    )

    assert summary.compacted_count == 1
    assert summary.deleted_ids == ["pref-duplicate"]
    assert _memory_ids(db_path) == ["pref-canonical"]
    assert vector_deletes == [("pref-duplicate", "mem:user-1")]


async def test_apply_is_scoped_to_requested_user_and_vector_namespace(tmp_path, monkeypatch):
    from fleetent import memory_layer

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
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-a",
        policy=memory_layer.MemoryMaintenancePolicy(),
        dry_run=False,
    )

    assert summary.deleted_ids == ["user-a-expired"]
    assert _memory_ids(db_path) == ["user-b-expired"]
    assert vector_deletes == [("user-a-expired", "mem:user-a")]
