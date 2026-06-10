"""Integration tests for shared-memory-lib (3c): shared_memory.db per-tenant routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fleetent.db import SQLiteDatabase
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter
from fleetent.vector_store.backend import SQLiteVectorBackend

# ── Task 1.1: tenant_scope returns shared memory handles ───────────────────


def test_tenant_scope_has_shared_memory_db(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    assert scope.shared_memory_db is not None
    assert isinstance(scope.shared_memory_db, SQLiteDatabase)


def test_tenant_scope_shared_memory_db_maps_to_tenant_dir(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("acme")
    assert scope.shared_memory_db.path == tmp_path / "acme" / "shared_memory.db"


def test_tenant_scope_has_shared_memory_vector_backend(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    assert scope.shared_memory_vector_backend is not None


def test_tenant_scope_shared_memory_vector_backend_maps_to_tenant_dir(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("acme")
    assert isinstance(scope.shared_memory_vector_backend, SQLiteVectorBackend)
    assert "acme" in scope.shared_memory_vector_backend.database_url
    assert "shared_memory_vectors.db" in scope.shared_memory_vector_backend.database_url


def test_tenant_scope_different_tenants_use_separate_shared_memory_dbs(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope_a = router.tenant_scope("tenant-a")
    scope_b = router.tenant_scope("tenant-b")
    assert scope_a.shared_memory_db.path != scope_b.shared_memory_db.path


def test_open_shared_memory_db_creates_schema(tmp_path: Path) -> None:
    from fleetent.memory.shared_memory_migrations import MIGRATIONS

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    db = scope.open_shared_memory_db(MIGRATIONS)
    assert db is scope.shared_memory_db
    result = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_memory_items'"
    )
    assert result.fetchone() is not None


def test_open_shared_memory_db_idempotent(tmp_path: Path) -> None:
    from fleetent.memory.shared_memory_migrations import MIGRATIONS

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    scope.open_shared_memory_db(MIGRATIONS)
    # second open must not raise SchemaTooNewError
    scope.open_shared_memory_db(MIGRATIONS)


# ── Task 2.1: shared.py connection from tenant_scope + vector routing ──────


def test_shared_py_exposes_set_shared_memory_db() -> None:
    from fleetent.memory import shared

    assert callable(getattr(shared, "set_shared_memory_db", None))


async def test_shared_py_uses_tenant_scope_db_not_store_db(tmp_path: Path) -> None:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    db = scope.open_shared_memory_db(MIGRATIONS)

    class _NullBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            pass

        async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    shared.set_shared_memory_db(db, _NullBackend())

    item = await shared.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="procedure",
        content="Team uses GitHub Flow.",
        created_by="user1",
    )
    # item must live in the tenant's shared_memory.db
    row = db.execute(
        "SELECT id FROM shared_memory_items WHERE id = :id", {"id": item.id}
    ).fetchone()
    assert row is not None


def test_shared_py_no_bare_sqlite3_connect() -> None:
    import inspect

    from fleetent.memory import shared

    source = inspect.getsource(shared)
    assert "sqlite3.connect" not in source


async def test_shared_memory_vector_uses_injected_backend(tmp_path: Path) -> None:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    db = scope.open_shared_memory_db(MIGRATIONS)

    calls: list[tuple[str, str, str]] = []

    class _TrackingBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            calls.append(("upsert", id, namespace))

        async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            calls.append(("delete", id, namespace))

        async def clear_namespace(self, namespace: str) -> None:
            pass

    shared.set_shared_memory_db(db, _TrackingBackend())

    item = await shared.create_shared_memory(
        scope_type="team",
        scope_id="eng",
        type="context",
        content="test content",
        created_by="user1",
    )
    assert any(
        op == "upsert" and id_ == item.id and ns == "shared:team:eng" for op, id_, ns in calls
    )


# ── Task 3.1: concurrent writes under WAL + busy_timeout ───────────────────


async def test_concurrent_writes_both_succeed(tmp_path: Path) -> None:
    """Two concurrent writers to shared_memory.db must both commit under WAL."""
    import asyncio

    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    db = scope.open_shared_memory_db(MIGRATIONS)

    async def _write(i: int) -> str:
        import uuid

        item_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO shared_memory_items
              (id, scope_type, scope_id, type, content, status, source,
               source_ref, created_by, created_at, updated_at)
            VALUES
              (:id, :scope_type, :scope_id, :type, :content, :status, :source,
               :source_ref, :created_by, :created_at, :updated_at)
            """,
            {
                "id": item_id,
                "scope_type": "team",
                "scope_id": "eng",
                "type": "context",
                "content": f"content-{i}",
                "status": "active",
                "source": "manual",
                "source_ref": None,
                "created_by": "writer",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        )
        return item_id

    id_a, id_b = await asyncio.gather(_write(1), _write(2))

    rows = db.execute(
        "SELECT id FROM shared_memory_items WHERE id IN (:a, :b)", {"a": id_a, "b": id_b}
    ).fetchall()
    assert {str(row["id"]) for row in rows} == {id_a, id_b}


async def test_read_does_not_block_concurrent_write(tmp_path: Path) -> None:
    """A reader can proceed while a writer is active (WAL allows concurrent read)."""
    import asyncio

    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    db = scope.open_shared_memory_db(MIGRATIONS)

    async def _write() -> None:
        import uuid

        db.execute(
            """
            INSERT INTO shared_memory_items
              (id, scope_type, scope_id, type, content, status, source,
               source_ref, created_by, created_at, updated_at)
            VALUES
              (:id, 'team', 'eng', 'context', 'val', 'active', 'manual',
               NULL, 'writer', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """,
            {"id": str(uuid.uuid4())},
        )

    async def _read() -> int:
        result = db.execute("SELECT COUNT(*) as cnt FROM shared_memory_items")
        row = result.fetchone()
        return int(row["cnt"]) if row else 0

    await asyncio.gather(_write(), _read())  # must not raise or deadlock
