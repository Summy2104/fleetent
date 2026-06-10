"""Tenant-scoped DB router: resolves per-tenant and per-agent physical backends.

Two flat typed resolvers:
  ``tenant_scope(tenant)`` → KbScope{kb_db, kb_vector_backend}   (per-tenant KB resources)
  ``agent_scope(tenant, agent_id)`` → AgentScope{state_db, vector_backend}  (per-agent state)

SQLite backend layout under ``<data_dir>/``::

  <tenant_id>/kb.db              — KB relation tables (Y-managed)
  <tenant_id>/kb_vectors.db      — KB vector store
  <tenant_id>/<agent_id>/agent_state.db   — agent state (Y-managed, 3b-1+)
  <tenant_id>/<agent_id>/agent_vectors.db — agent vector store

Directory structure is private to SQLiteTenantBackend; call sites only
express scope and get typed handles — they never see file paths.

Multi-tenant fan-out (3d) will extend SQLiteTenantBackend; call sites are
already abstracted and will not change.
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
    """Resolved scope for one tenant's KB resources."""

    tenant_id: str
    kb_db: SQLiteDatabase
    kb_vector_backend: VectorBackend

    def open_kb_db(self, migrations: list[tuple[int, str]]) -> SQLiteDatabase:
        """Run migrate-on-open against kb_db and return it.

        Idempotent: if the DB is already at current version nothing changes.
        """
        from fleetent.schema_migrations import migrate

        migrate(self.kb_db, migrations)
        return self.kb_db


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
        return KbScope(
            tenant_id=tenant_id,
            kb_db=kb_db,
            kb_vector_backend=kb_vector_backend,
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
