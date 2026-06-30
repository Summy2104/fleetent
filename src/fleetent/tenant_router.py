"""Tenant-scoped DB router: resolves per-tenant and per-agent physical backends.

Two flat typed resolvers:
  ``tenant_scope(tenant)`` → KbScope{kb_db, kb_vector_backend}
  ``agent_scope(tenant, agent_id)`` → AgentScope{state_db, vector_backend}

SQLite backend layout under ``<fleetent_home>/``::

  tenants/<tenant_id>/kb/data/kb.db                         — KB relation tables (Y-managed)
  tenants/<tenant_id>/kb/data/kb_vectors.db                 — KB vector store
  tenants/<tenant_id>/agents/<agent_id>/data/agent_state.db — state + agent_memory_items
  tenants/<tenant_id>/agents/<agent_id>/data/agent_vectors.db — mem:* + agentmem:* vector store

Directory structure is private to SQLiteTenantBackend; call sites only
express scope and get typed handles — they never see file paths.

Multi-tenant fan-out (3d): call sites pass the real tenant_id from agent config;
SQLiteTenantBackend maps each to its physical partition under ``<fleetent_home>/tenants/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase, create_substrate
from fleetent.paths import base_dir, tenant_kb_data_dir
from fleetent.vector_store.backend import SQLiteVectorBackend, VectorBackend

_KB_FILENAMES = ("kb.db", "kb_vectors.db")
_SQLITE_SIDECAR_SUFFIXES = ("", "-wal", "-shm")


@dataclass(frozen=True)
class VectorBackendHandle:
    """Thin wrapper giving a typed name to the resolved vector backend."""

    backend: VectorBackend


@dataclass(frozen=True)
class KbScope:
    """Resolved scope for one tenant's KB resources."""

    tenant_id: str
    kb_db: SQLiteDatabase
    kb_vector_backend: VectorBackend

    def open_kb_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against kb_db and return it.

        Idempotent: if the DB is already at current version nothing changes.
        """
        if self.kb_db.capabilities.embedded_migrations:
            from fleetent.schema_migrations import migrate

            migrate(self.kb_db, migrations)
        return self.kb_db

    def open_kb_db_ro(self) -> ReadOnlySQLiteDatabase:
        """Return a read-only handle to kb_db — no migration, no writes allowed.

        For platform-side projection only.  Raises if the DB file does not exist.
        """
        return ReadOnlySQLiteDatabase(path=self.kb_db.path)


@dataclass(frozen=True)
class AgentScope:
    """Resolved scope for one agent's private state and memory resources.

    agent_memory_items live in state_db (agent_state.db) since wire-agent-memory.
    The separate agent_memory.db file is retired, and agentmem vectors now share
    the single per-agent vector backend with mem:* namespaces.
    """

    state_db: SQLiteDatabase
    vector_backend: VectorBackend

    def open_state_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against state_db and return it.

        Idempotent: if the DB is already at current version nothing changes.
        """
        if self.state_db.capabilities.embedded_migrations:
            from fleetent.schema_migrations import migrate

            migrate(self.state_db, migrations)
        return self.state_db

    def open_state_db_ro(self) -> ReadOnlySQLiteDatabase:
        """Return a read-only handle to state_db — no migration, no writes allowed.

        For platform-side projection only.  Raises if the DB file does not exist.
        """
        return ReadOnlySQLiteDatabase(path=self.state_db.path)


class TenantBackend(Protocol):
    """Pluggable backend: resolves tenant/agent scopes to physical handles."""

    def resolve(self, tenant_id: str) -> KbScope: ...

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope: ...


@dataclass(frozen=True)
class SQLiteTenantBackend:
    """SQLite backend: maps each scope to files under ``<fleetent_home>/tenants/``."""

    data_dir: Path

    def resolve(self, tenant_id: str) -> KbScope:
        tenant_dir = self.data_dir / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        kb_dir = ensure_tenant_kb_dir(self.data_dir, tenant_id)
        kb_db = cast(SQLiteDatabase, create_substrate(f"sqlite:///{kb_dir / 'kb.db'}"))
        kb_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{kb_dir / 'kb_vectors.db'}"
        )
        return KbScope(
            tenant_id=tenant_id,
            kb_db=kb_db,
            kb_vector_backend=kb_vector_backend,
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        agent_dir = self.data_dir / "tenants" / tenant_id / "agents" / agent_id / "data"
        agent_dir.mkdir(parents=True, exist_ok=True)
        state_db = cast(
            SQLiteDatabase,
            create_substrate(f"sqlite:///{agent_dir / 'agent_state.db'}"),
        )
        vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{agent_dir / 'agent_vectors.db'}"
        )
        return AgentScope(
            state_db=state_db,
            vector_backend=vector_backend,
        )


@dataclass(frozen=True)
class StandaloneKBTenantBackend:
    """Standalone KB backend: flat KB files under one per-tenant service data dir."""

    data_dir: Path

    def resolve(self, tenant_id: str) -> KbScope:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        kb_db = cast(SQLiteDatabase, create_substrate(f"sqlite:///{self.data_dir / 'kb.db'}"))
        kb_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{self.data_dir / 'kb_vectors.db'}"
        )
        return KbScope(
            tenant_id=tenant_id,
            kb_db=kb_db,
            kb_vector_backend=kb_vector_backend,
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        return SQLiteTenantBackend(data_dir=self.data_dir).resolve_agent(tenant_id, agent_id)


@dataclass(frozen=True)
class TenantRouter:
    """Single entry point for tenant-scoped and agent-scoped resource resolution.

    Call sites only interact with this class; the backend is injected and
    can be swapped without touching call sites.
    """

    _backend: TenantBackend

    def tenant_scope(self, tenant_id: str) -> KbScope:
        """Resolve *tenant_id* to its KB relation DB and vector backend."""
        return self._backend.resolve(tenant_id)

    def agent_scope(self, tenant_id: str, agent_id: str) -> AgentScope:
        """Resolve *(tenant_id, agent_id)* to the agent's private state DB and vector backend."""
        return self._backend.resolve_agent(tenant_id, agent_id)


def ensure_tenant_kb_dir(data_dir: Path, tenant_id: str) -> Path:
    """Provision ``tenants/<tenant>/kb/data`` and migrate any legacy flat KB files into it."""
    tenant_root = data_dir / "tenants" / tenant_id
    tenant_root.mkdir(parents=True, exist_ok=True)
    kb_dir = data_dir / tenant_kb_data_dir(tenant_id).relative_to(base_dir())
    if kb_dir.exists():
        return kb_dir

    legacy_kb = tenant_root / "kb.db"
    if legacy_kb.exists():
        kb_dir.mkdir(parents=True, exist_ok=True)
        for filename in _KB_FILENAMES:
            for suffix in _SQLITE_SIDECAR_SUFFIXES:
                source = tenant_root / f"{filename}{suffix}"
                if source.exists():
                    source.replace(kb_dir / f"{filename}{suffix}")
        return kb_dir

    kb_dir.mkdir(parents=True, exist_ok=True)
    return kb_dir
