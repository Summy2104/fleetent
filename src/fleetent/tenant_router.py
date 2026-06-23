"""Tenant-scoped DB router: resolves per-tenant and per-agent physical backends.

Two flat typed resolvers:
  ``tenant_scope(tenant)`` → KbScope{kb_db, kb_vector_backend}
  ``agent_scope(tenant, agent_id)`` → AgentScope{state_db, vector_backend,
                                                   agent_memory_db, agent_memory_vector_backend}

SQLite backend layout under ``<data_dir>/``::

  <tenant_id>/kb.db                       — KB relation tables (Y-managed)
  <tenant_id>/kb_vectors.db               — KB vector store
  <tenant_id>/<agent_id>/agent_state.db   — agent state (Y-managed)
  <tenant_id>/<agent_id>/agent_vectors.db — agent vector store
  <tenant_id>/<agent_id>/agent_memory.db  — agent memory relation tables (Y-managed)
  <tenant_id>/<agent_id>/agent_memory_vectors.db — agent memory vector store (agentmem: family)

Directory structure is private to SQLiteTenantBackend; call sites only
express scope and get typed handles — they never see file paths.

Multi-tenant fan-out (3d): call sites pass the real tenant_id from agent config;
SQLiteTenantBackend maps each to its physical partition under ``<data_dir>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase, create_substrate
from fleetent.vector_store.backend import SQLiteVectorBackend, VectorBackend


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
    """Resolved scope for one agent's private state and memory resources."""

    state_db: SQLiteDatabase
    vector_backend: VectorBackend
    agent_memory_db: SQLiteDatabase | None = None
    agent_memory_vector_backend: VectorBackend | None = None

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

    def open_agent_memory_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against agent_memory_db and return it.

        Raises ValueError when agent_memory_db was not provisioned.
        Idempotent when already at current version.
        """
        if self.agent_memory_db is None:
            raise ValueError(
                "agent_memory_db not provisioned in this AgentScope — "
                "use SQLiteTenantBackend or supply agent_memory_db explicitly"
            )
        if self.agent_memory_db.capabilities.embedded_migrations:
            from fleetent.schema_migrations import migrate

            migrate(self.agent_memory_db, migrations)
        return self.agent_memory_db

    def open_agent_memory_db_ro(self) -> ReadOnlySQLiteDatabase:
        """Return a read-only handle to agent_memory_db — no migration, no writes.

        For platform-side projection only.  Raises if the DB file does not exist.
        """
        if self.agent_memory_db is None:
            raise ValueError(
                "agent_memory_db not provisioned in this AgentScope — "
                "use SQLiteTenantBackend or supply agent_memory_db explicitly"
            )
        return ReadOnlySQLiteDatabase(path=self.agent_memory_db.path)


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
        tenant_dir.mkdir(parents=True, exist_ok=True)
        kb_db = cast(SQLiteDatabase, create_substrate(f"sqlite:///{tenant_dir / 'kb.db'}"))
        kb_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{tenant_dir / 'kb_vectors.db'}"
        )
        return KbScope(
            tenant_id=tenant_id,
            kb_db=kb_db,
            kb_vector_backend=kb_vector_backend,
        )

    def resolve_agent(self, tenant_id: str, agent_id: str) -> AgentScope:
        agent_dir = self.data_dir / tenant_id / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        state_db = cast(
            SQLiteDatabase,
            create_substrate(f"sqlite:///{agent_dir / 'agent_state.db'}"),
        )
        vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{agent_dir / 'agent_vectors.db'}"
        )
        agent_memory_db = cast(
            SQLiteDatabase,
            create_substrate(f"sqlite:///{agent_dir / 'agent_memory.db'}"),
        )
        agent_memory_vector_backend = SQLiteVectorBackend(
            database_url=f"sqlite:///{agent_dir / 'agent_memory_vectors.db'}"
        )
        return AgentScope(
            state_db=state_db,
            vector_backend=vector_backend,
            agent_memory_db=agent_memory_db,
            agent_memory_vector_backend=agent_memory_vector_backend,
        )


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
