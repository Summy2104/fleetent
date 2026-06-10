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


# ── 2.3: platform registry traversal + read aggregation ─────────────────────


def _seed_agent_db(data_dir: Path, tenant_id: str, agent_id: str) -> None:
    """Helper: boot agent DB and insert a session + approval for testing."""
    from fleetent.runtime.agent_app import _init_agent_db_schema
    from fleetent.session import index as session_index

    db_url = f"sqlite:///{data_dir / f'fleet_{tenant_id}_{agent_id}.db'}"
    _init_agent_db_schema(db_url, agent_id=agent_id, tenant_id=tenant_id)

    # Insert a session row directly (session_index was set by _init_agent_db_schema)
    session_index.record_activity(
        session_id=f"sess-{tenant_id}-{agent_id}",
        user_id="user1",
        message_count=3,
        agent_name=agent_id,
    )


def test_aggregate_sessions_across_agents(tmp_path: Path) -> None:
    """Platform aggregates session counts from multiple agents via registry traversal."""
    from fleetent.platform import read_projection
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _seed_agent_db(data_dir, "tenant-1", "agent-a")
    _seed_agent_db(data_dir, "tenant-1", "agent-b")
    _seed_agent_db(data_dir, "tenant-2", "agent-c")

    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))

    agents = [
        ("tenant-1", "agent-a"),
        ("tenant-1", "agent-b"),
        ("tenant-2", "agent-c"),
    ]

    total = read_projection.aggregate_session_counts_across_agents(router, agents)
    assert total >= 3, f"Expected at least 3 sessions (one per agent), got {total}"


def test_aggregate_approvals_across_agents_read_only(tmp_path: Path) -> None:
    """Platform aggregates approvals across agents using read-only DBs."""
    import datetime

    from fleetent.governance import approval_store
    from fleetent.platform import read_projection
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Seed two agents with approvals
    for tid, aid in [("t1", "bot"), ("t2", "bot")]:
        _seed_agent_db(data_dir, tid, aid)
        approval_store.insert_approval(
            id=f"appr-{tid}-{aid}",
            session_id=f"sess-{tid}-{aid}",
            requester_user_id="user1",
            risk_level="medium",
            tool_name="bash",
            tool_args="{}",
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))
    agents = [("t1", "bot"), ("t2", "bot")]

    approvals = read_projection.aggregate_approvals_across_agents(router, agents)
    assert len(approvals) >= 2, f"Expected 2 approvals (one per agent), got {len(approvals)}"
    agent_names = {a["agent_id"] for a in approvals}
    assert "bot" in agent_names


def test_read_shared_memory_for_tenant(tmp_path: Path) -> None:
    """Platform reads shared memory for a tenant directly (per-tenant, read-only)."""
    from fleetent.memory import shared as shared_memory
    from fleetent.memory.shared_memory_migrations import MIGRATIONS as SHARED_MEMORY_MIGRATIONS
    from fleetent.platform import read_projection
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Set up shared memory for tenant-1 (write side)
    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))
    kb_scope = router.tenant_scope("tenant-1")
    sm_db = kb_scope.open_shared_memory_db(SHARED_MEMORY_MIGRATIONS)
    shared_memory.set_shared_memory_db(sm_db, kb_scope.shared_memory_vector_backend)  # type: ignore[arg-type]

    # Platform reads shared memory read-only
    rows = read_projection.read_shared_memory_for_tenant(router, "tenant-1")
    assert isinstance(rows, list)  # returns a list (may be empty if no items seeded)


def test_registry_traversal_no_write_to_agent_dbs(tmp_path: Path) -> None:
    """Registry traversal must not change user_version on any agent DB."""
    from fleetent.platform import read_projection
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _seed_agent_db(data_dir, "tenant-1", "bot")
    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))

    # Record user_version before traversal
    state_db_path = data_dir / "tenant-1" / "bot" / "agent_state.db"
    version_before = _user_version(state_db_path)

    # Traverse and aggregate
    read_projection.aggregate_session_counts_across_agents(router, [("tenant-1", "bot")])

    # user_version must be unchanged
    version_after = _user_version(state_db_path)
    assert version_after == version_before, "Read-only traversal must not mutate user_version"


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
