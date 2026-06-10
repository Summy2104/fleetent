"""Tests: router ↔ engine integration — opening a scope triggers migrate-on-open."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return ver


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def test_open_scope_triggers_migrate_on_open(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.scope("default")

    # Opening the scope with migrations applied should build the schema.
    scope.open_kb_db(KB_MIGRATIONS)

    db_path = scope.kb_db.path
    assert _user_version(db_path) == max(v for v, _ in KB_MIGRATIONS)
    assert "knowledge_bases" in _table_names(db_path)


def test_open_scope_twice_is_idempotent(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.scope("default")

    scope.open_kb_db(KB_MIGRATIONS)
    scope.open_kb_db(KB_MIGRATIONS)  # second call must not raise

    db_path = scope.kb_db.path
    assert _user_version(db_path) == max(v for v, _ in KB_MIGRATIONS)


def test_open_scope_returns_the_same_db(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.scope("default")

    db = scope.open_kb_db(KB_MIGRATIONS)
    assert db is scope.kb_db


def test_two_tenants_migrate_independently(tmp_path: Path) -> None:
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    scope_a = router.scope("tenant-a")
    scope_b = router.scope("tenant-b")

    scope_a.open_kb_db(KB_MIGRATIONS)
    scope_b.open_kb_db(KB_MIGRATIONS)

    assert scope_a.kb_db.path != scope_b.kb_db.path
    assert _user_version(scope_a.kb_db.path) == max(v for v, _ in KB_MIGRATIONS)
    assert _user_version(scope_b.kb_db.path) == max(v for v, _ in KB_MIGRATIONS)
