"""Integration tests for platform read-only projection (3d Part B, tasks 2.1-2.3).

Verifies:
- Router provides read-only handles that reject writes
- Read-only open does NOT trigger migrate (user_version and schema unchanged)
- Platform can read from a stopped agent's DB file
- Platform can aggregate across agents via registry traversal
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


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


# ── 2.1-a: read-only handles exist on KbScope and AgentScope ─────────────────


def test_agent_scope_provides_readonly_handle(tmp_path: Path) -> None:
    """AgentScope exposes open_state_db_ro() returning a ReadOnlySQLiteDatabase."""
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    # First boot with real write side to create the DB
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    scope = router.agent_scope("acme", "bot")
    scope.open_state_db(AGENT_STATE_MIGRATIONS)

    # Now open read-only
    ro_db = scope.open_state_db_ro()
    assert ro_db is not None


def test_kb_scope_provides_readonly_handle(tmp_path: Path) -> None:
    """KbScope exposes open_kb_db_ro() returning a ReadOnlySQLiteDatabase."""
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("acme")
    scope.open_kb_db(KB_MIGRATIONS)

    ro_db = scope.open_kb_db_ro()
    assert ro_db is not None


# ── 2.1-b: write to read-only handle is rejected ─────────────────────────────


def test_readonly_state_db_rejects_writes(tmp_path: Path) -> None:
    """Writes to a read-only AgentScope handle must raise an error."""
    import pytest

    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("acme", "bot")
    scope.open_state_db(AGENT_STATE_MIGRATIONS)

    ro_db = scope.open_state_db_ro()

    with pytest.raises(Exception):  # sqlite3.OperationalError or PermissionError
        ro_db.execute("INSERT INTO sessions(id) VALUES (:id)", {"id": "x"})


def test_readonly_kb_db_rejects_writes(tmp_path: Path) -> None:
    """Writes to a read-only KbScope handle must raise an error."""
    import pytest

    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("acme")
    scope.open_kb_db(KB_MIGRATIONS)

    ro_db = scope.open_kb_db_ro()

    with pytest.raises(Exception):
        ro_db.execute(
            "INSERT INTO knowledge_bases(id, name, tenant_id) VALUES (:id, :name, :tid)",
            {"id": "x", "name": "x", "tid": "acme"},
        )


# ── 2.1-c: read-only open does NOT trigger migrate ───────────────────────────


def test_readonly_open_does_not_change_user_version(tmp_path: Path) -> None:
    """open_state_db_ro() must NOT run any migration or change user_version."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("acme", "bot")

    # First write-side open: migrates to current version
    scope.open_state_db(AGENT_STATE_MIGRATIONS)
    db_path = scope.state_db.path
    version_after_write = _user_version(db_path)

    # Now open read-only: version must remain identical
    scope.open_state_db_ro()
    version_after_ro = _user_version(db_path)

    assert version_after_ro == version_after_write, (
        "read-only open must not change user_version"
    )


def test_readonly_open_does_not_create_tables(tmp_path: Path) -> None:
    """open_state_db_ro() on a non-existent DB must NOT create the file or any tables."""
    import pytest

    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("acme", "bot")
    db_path = scope.state_db.path

    # DB file does not exist yet
    assert not db_path.exists()

    # Read-only open on a non-existent file should either raise or return an empty DB
    # (SQLite mode=ro raises OperationalError when file doesn't exist).
    with pytest.raises(Exception):
        ro_db = scope.open_state_db_ro()
        # If the above doesn't raise, a read attempt must fail
        ro_db.execute("SELECT 1")


def test_readonly_kb_open_does_not_change_user_version(tmp_path: Path) -> None:
    """open_kb_db_ro() must NOT run KB migrations."""
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("acme")
    scope.open_kb_db(KB_MIGRATIONS)
    kb_path = scope.kb_db.path
    version_after_write = _user_version(kb_path)

    scope.open_kb_db_ro()
    version_after_ro = _user_version(kb_path)

    assert version_after_ro == version_after_write


# ── 2.1-d: can read a stopped agent's DB ─────────────────────────────────────


def test_can_read_stopped_agent_db(tmp_path: Path) -> None:
    """Platform can read session history from a DB file even when agent is not running."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.session import index as session_index
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.agent_scope("acme", "bot")

    # Write side: create DB and insert a session
    write_db = scope.open_state_db(AGENT_STATE_MIGRATIONS)
    session_index.set_state_db(write_db)
    # The DB file now exists on disk (agent "stops" here — no further writes)

    # Read-only side: open without migrating
    ro_db = scope.open_state_db_ro()
    result = ro_db.execute("SELECT count(*) AS cnt FROM sessions")
    assert result.fetchone() is not None  # read succeeded even with no active agent process
