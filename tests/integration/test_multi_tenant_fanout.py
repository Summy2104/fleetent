"""Integration tests for multi-tenant fan-out (3d Part A).

Verifies:
- _init_agent_db_schema routes by actual tenant_id (not hardcoded 'default')
- Agent state DB and KB land under <tenant>/ directory
- T1 agent physically cannot reach T2 databases (path isolation)
- Directory provisioning happens lazily on first open
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _tables_in(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }


def _db_paths_under(root: Path) -> set[Path]:
    """Collect all .db files recursively under root."""
    return set(root.rglob("*.db"))


# ── 1.1-a: routes by agent's tenant_id, not hardcoded 'default' ────────────


def test_init_agent_db_schema_routes_by_tenant_id(tmp_path: Path) -> None:
    """When tenant_id='acme', all agent DBs land under tenants/acme/, not tenants/default/."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="bot", tenant_id="acme")

    # KB must be under tenants/<tenant>/
    kb_path = tmp_path / "tenants" / "acme" / "kb" / "data" / "kb.db"
    assert kb_path.exists(), "KB must be at tenants/acme/kb/data/kb.db, not default/"

    # Agent state must be under tenants/<tenant>/agents/<agent_id>/data/
    state_path = tmp_path / "tenants" / "acme" / "agents" / "bot" / "data" / "agent_state.db"
    assert state_path.exists(), "Agent state must be at tenants/acme/agents/bot/data/agent_state.db"

    # No 'default' directory should be created
    assert not (tmp_path / "tenants" / "default").exists(), (
        "Must not fall back to 'default' when tenant_id given"
    )


def test_init_agent_db_schema_default_tenant_still_works(tmp_path: Path) -> None:
    """Backward compat: omitting tenant_id (or passing 'default') uses tenants/default/."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # default tenant — no tenant_id arg (backward compat)
    _init_agent_db_schema(data_dir, agent_id="bot")

    kb_path = tmp_path / "tenants" / "default" / "kb" / "data" / "kb.db"
    assert kb_path.exists(), "Default tenant KB must be at tenants/default/kb/data/kb.db"
    state_path = tmp_path / "tenants" / "default" / "agents" / "bot" / "data" / "agent_state.db"
    assert state_path.exists(), (
        "Default tenant state must be at tenants/default/agents/bot/data/agent_state.db"
    )


# ── 1.1-b: KB tables land in tenant-scoped KB db ───────────────────────────


def test_kb_tables_land_in_tenant_scoped_db(tmp_path: Path) -> None:
    """KB tables land in acme/kb/data/kb.db, not in the main agent db."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="bot", tenant_id="acme")

    kb_path = tmp_path / "tenants" / "acme" / "kb" / "data" / "kb.db"
    tables = _tables_in(kb_path)
    assert "knowledge_bases" in tables
    assert "knowledge_chunks" in tables


# ── 1.1-c: physical isolation — T1 agent cannot reach T2 databases ──────────


def test_tenant_physical_isolation_different_agents(tmp_path: Path) -> None:
    """T1/agent-a and T2/agent-b have non-overlapping db paths."""
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    t1_scope = router.agent_scope("tenant-1", "agent-a")
    t2_scope = router.agent_scope("tenant-2", "agent-b")

    t1_state = t1_scope.state_db.path
    t2_state = t2_scope.state_db.path

    assert t1_state != t2_state
    # T1 path must be strictly inside tenant-1/
    assert "tenant-1" in str(t1_state)
    assert "tenant-2" not in str(t1_state), "T1 agent must not reach T2 directory"
    # T2 path must be strictly inside tenant-2/
    assert "tenant-2" in str(t2_state)
    assert "tenant-1" not in str(t2_state), "T2 agent must not reach T1 directory"


def test_tenant_physical_isolation_kb_scopes(tmp_path: Path) -> None:
    """T1 and T2 KB databases are in separate directories."""
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    t1_kb = router.tenant_scope("tenant-1").kb_db.path
    t2_kb = router.tenant_scope("tenant-2").kb_db.path

    assert t1_kb != t2_kb
    assert "tenant-1" in str(t1_kb)
    assert "tenant-1" not in str(t2_kb)
    assert "tenant-2" in str(t2_kb)
    assert "tenant-2" not in str(t1_kb)


def test_two_agent_boots_different_tenants_no_cross_contamination(tmp_path: Path) -> None:
    """Booting agents for T1 and T2 creates separate DB files with no cross-contamination."""
    from fleetent.runtime.agent_app import _init_agent_db_schema

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Boot T1/bot
    _init_agent_db_schema(data_dir, agent_id="bot", tenant_id="tenant-1")

    # Boot T2/bot (same agent name, different tenant)
    _init_agent_db_schema(data_dir, agent_id="bot", tenant_id="tenant-2")

    t1_state = tmp_path / "tenants" / "tenant-1" / "agents" / "bot" / "data" / "agent_state.db"
    t2_state = tmp_path / "tenants" / "tenant-2" / "agents" / "bot" / "data" / "agent_state.db"

    assert t1_state.exists(), "T1 agent state DB must exist"
    assert t2_state.exists(), "T2 agent state DB must exist"
    assert t1_state != t2_state

    # T1 directory must not contain T2 db files and vice versa
    t1_dbs = _db_paths_under(tmp_path / "tenants" / "tenant-1")
    t2_dbs = _db_paths_under(tmp_path / "tenants" / "tenant-2")
    assert t1_dbs.isdisjoint(t2_dbs), "T1 and T2 database sets must be fully disjoint"
