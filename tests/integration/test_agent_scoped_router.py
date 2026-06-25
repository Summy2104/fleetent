"""Tests for per-agent scope in TenantRouter (3b-1).

Verifies:
- agent_scope(tenant, agent_id) returns AgentScope{state_db, vector_backend}
- SQLite backend maps to tenants/<tenant>/agents/<agent_id>/data/agent_state.db + agent_vectors.db
- tenant_scope and agent_scope are flat peers (not nested)
- Backend replaceable: injecting a fake backend leaves call sites unchanged
- open_state_db(migrations) runs migrate-on-open and returns state_db
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path
from typing import Any

from fleetent.db import SQLiteDatabase
from fleetent.tenant_router import (
    AgentScope,
    KbScope,
    SQLiteTenantBackend,
    TenantRouter,
)
from fleetent.vector_store.backend import SQLiteVectorBackend


class _FakeVectorBackend:
    """Minimal VectorBackend stub."""

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        pass

    async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
        return []

    async def delete(self, id: str, namespace: str) -> None:
        pass

    async def clear_namespace(self, namespace: str) -> None:
        pass


# ── 1: agent_scope returns AgentScope ──────────────────────────────────────


def test_agent_scope_returns_agent_scope(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    result = router.agent_scope("default", "my-agent")
    assert isinstance(result, AgentScope)
    assert isinstance(result.state_db, SQLiteDatabase)
    assert result.vector_backend is not None
    assert {f.name for f in dataclasses.fields(AgentScope)} == {"state_db", "vector_backend"}


# ── 2: SQLite backend path mapping ─────────────────────────────────────────


def test_sqlite_backend_agent_state_db_path(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("default", "my-agent")
    assert scope.state_db.path == (
        tmp_path / "tenants" / "default" / "agents" / "my-agent" / "data" / "agent_state.db"
    )


def test_sqlite_backend_agent_vectors_db_path(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("default", "my-agent")
    expected = str(
        tmp_path / "tenants" / "default" / "agents" / "my-agent" / "data" / "agent_vectors.db"
    )
    assert isinstance(scope.vector_backend, SQLiteVectorBackend)
    assert expected in scope.vector_backend.database_url


def test_different_agents_get_different_paths(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope_a = router.agent_scope("default", "agent-a")
    scope_b = router.agent_scope("default", "agent-b")
    assert scope_a.state_db.path != scope_b.state_db.path
    assert "agent-a" in str(scope_a.state_db.path)
    assert "agent-b" in str(scope_b.state_db.path)


def test_different_tenants_get_different_paths(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope_a = router.agent_scope("tenant-a", "bot")
    scope_b = router.agent_scope("tenant-b", "bot")
    assert scope_a.state_db.path != scope_b.state_db.path
    assert scope_a.state_db.path.is_relative_to(tmp_path / "tenants" / "tenant-a")
    assert scope_b.state_db.path.is_relative_to(tmp_path / "tenants" / "tenant-b")


# ── 3: tenant_scope and agent_scope are flat peers ─────────────────────────


def test_tenant_scope_and_agent_scope_are_peers(tmp_path: Path) -> None:
    """Neither resolver wraps the other; each returns its own typed scope."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    tenant_s = router.tenant_scope("default")
    agent_s = router.agent_scope("default", "my-agent")
    assert isinstance(tenant_s, KbScope)
    assert isinstance(agent_s, AgentScope)
    assert not isinstance(agent_s, KbScope)
    assert not isinstance(tenant_s, AgentScope)


# ── 4: open_state_db runs migrate-on-open ──────────────────────────────────


def test_open_state_db_returns_state_db(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("default", "my-agent")
    migrations: list[tuple[int, str]] = [(1, "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY)")]
    db = scope.open_state_db(migrations)
    assert db is scope.state_db


def test_open_state_db_runs_migrations(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("default", "my-agent")
    migrations: list[tuple[int, str]] = [
        (1, "CREATE TABLE IF NOT EXISTS hello (id TEXT PRIMARY KEY)")
    ]
    scope.open_state_db(migrations)
    conn = sqlite3.connect(scope.state_db.path)
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    assert "hello" in tables


def test_open_state_db_is_idempotent(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("default", "my-agent")
    migrations: list[tuple[int, str]] = [(1, "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY)")]
    scope.open_state_db(migrations)
    scope.open_state_db(migrations)  # second call must not raise


# ── 5: backend is replaceable ─────────────────────────────────────────────


class _FakeAgentBackend:
    """Fake backend recording calls; confirms call sites are unchanged on swap."""

    def __init__(self, fake_db_path: Path, fake_vector: _FakeVectorBackend) -> None:
        self._db_path = fake_db_path
        self._vector = fake_vector
        self.resolve_calls: list[str] = []
        self.resolve_agent_calls: list[tuple[str, str]] = []

    def resolve(self, tenant_id: str) -> KbScope:
        self.resolve_calls.append(tenant_id)
        return KbScope(
            tenant_id=tenant_id,
            kb_db=SQLiteDatabase(path=self._db_path),
            kb_vector_backend=self._vector,  # type: ignore[arg-type]
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        self.resolve_agent_calls.append((tenant_id, agent_id))
        return AgentScope(
            state_db=SQLiteDatabase(path=self._db_path),
            vector_backend=self._vector,  # type: ignore[arg-type]
        )


def test_agent_backend_is_replaceable(tmp_path: Path) -> None:
    fake_vector = _FakeVectorBackend()
    fake_db = tmp_path / "fake.db"
    fake_backend = _FakeAgentBackend(fake_db, fake_vector)

    router = TenantRouter(fake_backend)
    scope = router.agent_scope("default", "my-agent")

    assert scope.state_db.path == fake_db
    assert scope.vector_backend is fake_vector
    assert fake_backend.resolve_agent_calls == [("default", "my-agent")]


def test_replacing_backend_does_not_change_agent_call_sites(tmp_path: Path) -> None:
    """Call site only calls router.agent_scope(tenant, agent_id); backend swap is invisible."""

    def call_site(router: TenantRouter, tenant: str, agent_id: str) -> AgentScope:
        return router.agent_scope(tenant, agent_id)

    # Real backend
    real_router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    real_scope = call_site(real_router, "default", "bot")
    assert isinstance(real_scope.state_db, SQLiteDatabase)

    # Fake backend — identical call site
    fake_router = TenantRouter(_FakeAgentBackend(tmp_path / "f.db", _FakeVectorBackend()))
    fake_scope = call_site(fake_router, "default", "bot")
    assert fake_scope.state_db.path == tmp_path / "f.db"
