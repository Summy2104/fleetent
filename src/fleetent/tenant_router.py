"""Tenant-scoped DB router: maps tenant_id to physical KB backends.

Usage::

    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir()))
    scope = router.scope("default")
    db = scope.kb_db                  # SQLiteDatabase for KB relation tables
    vec = scope.kb_vector_backend     # VectorBackend handle for KB vectors

The SQLite backend puts each tenant's KB under ``<data_dir>/<tenant_id>/``:
  - ``<tenant_id>/kb.db``         — KB relation tables (Y-managed)
  - ``<tenant_id>/kb_vectors.db`` — KB vector store

Multi-tenant fan-out (3b) will extend SQLiteTenantBackend; call sites are
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


class TenantBackend(Protocol):
    """Pluggable backend: resolves a tenant_id to its physical KB handles."""

    def resolve(self, tenant_id: str) -> KbScope: ...


@dataclass(frozen=True)
class SQLiteTenantBackend:
    """SQLite backend: maps each tenant to files under ``<data_dir>/<tenant_id>/``."""

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


@dataclass(frozen=True)
class TenantRouter:
    """Single entry point for tenant-scoped KB resource resolution.

    Call sites only interact with this class; the backend is injected and
    can be swapped without touching call sites.
    """

    _backend: TenantBackend

    def scope(self, tenant_id: str) -> KbScope:
        """Resolve *tenant_id* to its KB relation DB and vector backend."""
        return self._backend.resolve(tenant_id)
