"""Tests for the tenant-scoped DB router.

Verifies:
- tenant_scope(tenant) resolves to {kb_db, kb_vector_backend}
- Both resolved from one tenant_scope call (same tenant binding)
- SQLite backend maps default scope to <fleetent_home>/tenants/default/kb/kb.db
- Backend is replaceable without changing call sites
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from typing import Any

from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.tenant_router import (
    AgentScope,
    KbScope,
    SQLiteTenantBackend,
    TenantRouter,
)


class _FakeVectorBackend:
    """Trivial stub implementing VectorBackend Protocol."""

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        pass

    async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
        return []

    async def delete(self, id: str, namespace: str) -> None:
        pass

    async def clear_namespace(self, namespace: str) -> None:
        pass


# ── 3.1-a: scope returns KbScope with kb_db and kb_vector_backend ──────────


def test_scope_returns_kb_scope(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    result = router.tenant_scope("default")
    assert isinstance(result, KbScope)
    assert isinstance(result.kb_db, SQLiteDatabase)
    assert result.kb_vector_backend is not None


# ── 3.1-b: kb_db and kb_vector_backend are from the same scope call ────────


def test_scope_single_call_binds_both_backends(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")

    # Both attributes are populated from one scope() call — verifying the
    # contract that "二者同源于一次解析" (design §3.1).
    assert scope.kb_db is not None
    assert scope.kb_vector_backend is not None
    # The same scope object owns both handles.
    assert scope.tenant_id == "default"


# ── 3.1-c: SQLite backend maps default scope to <fleetent_home>/tenants/default/ files ──


def test_sqlite_backend_maps_default_to_tenant_directory(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")

    assert isinstance(scope.kb_db, SQLiteDatabase)
    assert scope.kb_db.path == tmp_path / "tenants" / "default" / "kb" / "kb.db"
    assert scope.kb_vector_backend.database_url == (
        f"sqlite:///{tmp_path / 'tenants' / 'default' / 'kb' / 'kb_vectors.db'}"
    )


def test_sqlite_backend_different_tenants_use_different_directories(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    scope_a = router.tenant_scope("tenant-a")
    scope_b = router.tenant_scope("tenant-b")

    assert scope_a.kb_db.path != scope_b.kb_db.path
    assert scope_a.kb_db.path == tmp_path / "tenants" / "tenant-a" / "kb" / "kb.db"
    assert scope_b.kb_db.path == tmp_path / "tenants" / "tenant-b" / "kb" / "kb.db"


# ── 3.1-d: backend is replaceable (inject fake backend) ────────────────────


class _FakeTenantBackend:
    """Fake backend that records calls; allows verifying call sites are unchanged."""

    def __init__(self, fake_db_path: Path, fake_vector: _FakeVectorBackend) -> None:
        self._db_path = fake_db_path
        self._vector = fake_vector
        self.scope_calls: list[str] = []

    def resolve(self, tenant_id: str) -> KbScope:
        self.scope_calls.append(tenant_id)
        return KbScope(
            tenant_id=tenant_id,
            kb_db=SQLiteDatabase(path=self._db_path),
            kb_vector_backend=self._vector,
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        return AgentScope(
            state_db=SQLiteDatabase(path=self._db_path),
            vector_backend=self._vector,  # type: ignore[arg-type]
        )


def test_backend_is_replaceable(tmp_path: Path) -> None:
    fake_vector = _FakeVectorBackend()
    fake_db_path = tmp_path / "fake.db"
    fake_backend = _FakeTenantBackend(fake_db_path, fake_vector)

    router = TenantRouter(fake_backend)
    scope = router.tenant_scope("default")

    assert scope.kb_db.path == fake_db_path
    assert scope.kb_vector_backend is fake_vector
    assert fake_backend.scope_calls == ["default"]


def test_replacing_backend_does_not_change_call_sites(tmp_path: Path) -> None:
    """Call sites only call router.tenant_scope(tenant_id) — not changed by backend swap."""

    # Call site code — identical regardless of which backend is injected:
    def call_site(router: TenantRouter, tenant_id: str) -> KbScope:
        return router.tenant_scope(tenant_id)

    # Real backend.
    real_router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    real_scope = call_site(real_router, "default")
    assert isinstance(real_scope.kb_db, SQLiteDatabase)

    # Fake backend — same call site, different backend.
    fake_router = TenantRouter(_FakeTenantBackend(tmp_path / "f.db", _FakeVectorBackend()))
    fake_scope = call_site(fake_router, "default")
    assert fake_scope.kb_db.path == tmp_path / "f.db"


def test_sqlite_tenant_backend_uses_substrate_factory() -> None:
    source = inspect.getsource(SQLiteTenantBackend)

    assert "create_substrate(" in source
    assert "SQLiteDatabase(path=" not in source


def _write_sqlite_marker(db_path: Path, table_name: str, value: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"CREATE TABLE {table_name} (value TEXT)")
        conn.execute(f"INSERT INTO {table_name}(value) VALUES (?)", (value,))
        conn.commit()


def test_resolve_migrates_flat_tenant_kb_into_kb_directory_before_open(tmp_path: Path) -> None:
    tenant_dir = tmp_path / "tenants" / "acme"
    tenant_dir.mkdir(parents=True)
    legacy_kb = tenant_dir / "kb.db"
    legacy_vectors = tenant_dir / "kb_vectors.db"
    _write_sqlite_marker(legacy_kb, "legacy_marker", "kb")
    _write_sqlite_marker(legacy_vectors, "legacy_vector_marker", "vec")
    for suffix in ("-wal", "-shm"):
        (tenant_dir / f"kb.db{suffix}").write_text(f"kb{suffix}", encoding="utf-8")
        (tenant_dir / f"kb_vectors.db{suffix}").write_text(f"vec{suffix}", encoding="utf-8")

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    scope = router.tenant_scope("acme")

    kb_dir = tmp_path / "tenants" / "acme" / "kb"
    assert scope.kb_db.path == kb_dir / "kb.db"
    assert kb_dir.is_dir()
    assert not legacy_kb.exists()
    assert not legacy_vectors.exists()
    for filename in (
        "kb.db",
        "kb.db-wal",
        "kb.db-shm",
        "kb_vectors.db",
        "kb_vectors.db-wal",
        "kb_vectors.db-shm",
    ):
        assert (kb_dir / filename).exists()

    scope.open_kb_db(KB_MIGRATIONS)
    with sqlite3.connect(scope.kb_db.path) as conn:
        assert conn.execute("SELECT value FROM legacy_marker").fetchone() == ("kb",)

    with sqlite3.connect(kb_dir / "kb_vectors.db") as conn:
        assert conn.execute("SELECT value FROM legacy_vector_marker").fetchone() == ("vec",)

    scope_again = router.tenant_scope("acme")
    assert scope_again.kb_db.path == scope.kb_db.path
    assert not legacy_kb.exists()
    assert not legacy_vectors.exists()
