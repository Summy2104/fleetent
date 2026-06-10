"""Tenant-scoped DB router: resolves per-tenant and per-agent physical backends.

Two flat typed resolvers:
  ``tenant_scope(tenant)`` → KbScope{kb_db, kb_vector_backend,
                                      shared_memory_db, shared_memory_vector_backend}
  ``agent_scope(tenant, agent_id)`` → AgentScope{state_db, vector_backend}

SQLite backend layout under ``<data_dir>/``::

  <tenant_id>/kb.db                     — KB relation tables (Y-managed)
  <tenant_id>/kb_vectors.db             — KB vector store
  <tenant_id>/shared_memory.db          — shared memory relation tables (Y-managed, 3c)
  <tenant_id>/shared_memory_vectors.db  — shared memory vector store (shared: family)
  <tenant_id>/<agent_id>/agent_state.db   — agent state (Y-managed, 3b-1+)
  <tenant_id>/<agent_id>/agent_vectors.db — agent vector store

Directory structure is private to SQLiteTenantBackend; call sites only
express scope and get typed handles — they never see file paths.

Multi-tenant fan-out (3d): call sites pass the real tenant_id from agent config;
SQLiteTenantBackend maps each to its physical partition under ``<data_dir>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fleetent.db import SQLiteDatabase
from fleetent.vector_store.backend import SQLiteVectorBackend, VectorBackend


@dataclass(frozen=True)
class VectorBackendHandle:
    """Thin wrapper giving a typed name to the resolved vector backend."""

    backend: VectorBackend


@dataclass(frozen=True)
class KbScope:
    """Resolved scope for one tenant's KB + shared memory resources.

    Fields added in 3c (shared-memory-lib):
      shared_memory_db            — per-tenant shared_memory.db (read-write; agents write)
      shared_memory_vector_backend — shared: family vector backend for this tenant
    """

    tenant_id: str
    kb_db: SQLiteDatabase
    kb_vector_backend: VectorBackend
    shared_memory_db: SQLiteDatabase | None = None
    shared_memory_vector_backend: VectorBackend | None = None

    def open_kb_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against kb_db and return it.

        Idempotent: if the DB is already at current version nothing changes.
        """
        from fleetent.schema_migrations import migrate

        migrate(self.kb_db, migrations)
        return self.kb_db

    def open_shared_memory_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against shared_memory_db and return it.

        Raises ValueError when shared_memory_db was not provisioned (e.g. fake backends
        created without the new fields).  Idempotent when already at current version.
        """
        if self.shared_memory_db is None:
            raise ValueError(
                "shared_memory_db not provisioned in this KbScope — "
                "use SQLiteTenantBackend or supply shared_memory_db explicitly"
            )
        from fleetent.schema_migrations import migrate

        migrate(self.shared_memory_db, migrations)
        return self.shared_memory_db


@dataclass(frozen=True)
class AgentScope:
    """Resolved scope for one agent's private state resources."""

    state_db: SQLiteDatabase
    vector_backend: VectorBackend

    def open_state_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against state_db and return it.

        Idempotent: if the DB is already at current version nothing changes.
        """
        from fleetent.schema_migrations import migrate

        migrate(self.state_db, migrations)
        return self.state_db


class TenantBackend(Protocol):
    """Pluggable backend: resolves tenant/agent scopes to physical handles."""

    def resolve(self, tenant_id: str) -> KbScope: ...

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope: ...


@dataclass(frozen=True)
class SQLiteTenantBackend:
    """SQLite backend: maps each scope to files under ``<data_dir>/``."""

    data_dir: Path

    def resolve(self, tenant_id: str) -> KbScope:
        tenant_dir = self.data_dir / tenant_id
        kb_db = SQLiteDatabase(path=tenant_dir / "kb.db")
        kb_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{tenant_dir / 'kb_vectors.db'}"
        )
        shared_memory_db = SQLiteDatabase(path=tenant_dir / "shared_memory.db")
        shared_memory_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{tenant_dir / 'shared_memory_vectors.db'}"
        )
        return KbScope(
            tenant_id=tenant_id,
            kb_db=kb_db,
            kb_vector_backend=kb_vector_backend,
            shared_memory_db=shared_memory_db,
            shared_memory_vector_backend=shared_memory_vector_backend,
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        agent_dir = self.data_dir / tenant_id / agent_id
        state_db = SQLiteDatabase(path=agent_dir / "agent_state.db")
        vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{agent_dir / 'agent_vectors.db'}"
        )
        return AgentScope(state_db=state_db, vector_backend=vector_backend)


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
