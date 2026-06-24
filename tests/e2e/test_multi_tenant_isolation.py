"""E2E: multi-tenant data isolation in the managed stack.

Verifies that two tenants running on the same node have:
1. Separate per-tenant data root directories.
2. Zero cross-tenant data bleed via the agent-memory read path.
3. Physically disjoint SQLite files (file-level isolation).

Lane: slow/nightly — runs under ``make test-e2e``, NOT in ``make test-pr``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from tests.e2e._path_helpers import agent_home_dir
from tests.e2e._tenant_helpers import TwoTenantStack

pytest_plugins = ["tests.e2e._tenant_helpers"]

_INSERT_SQL = (
    "INSERT INTO agent_memory_items "
    "(id, type, content, status, source, source_ref, created_by, created_at, updated_at)"
    " VALUES"
    " (:id, :type, :content, :status, :source, :source_ref,"
    " :created_by, :created_at, :updated_at)"
)
_NOW = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# E2E-0  fixture smoke — both agents ready, data roots independent
# ---------------------------------------------------------------------------


def test_two_tenant_agents_ready_and_data_roots_independent(
    managed_stack_two_tenants: TwoTenantStack,
) -> None:
    stack = managed_stack_two_tenants
    assert stack.agent_a_status["phase"] == "running"
    assert stack.agent_a_status["health"] == "healthy"
    assert stack.agent_b_status["phase"] == "running"
    assert stack.agent_b_status["health"] == "healthy"

    data_root_a = (
        agent_home_dir(stack.home_dir, stack.agent_a_name, tenant_id=stack.tenant_a_id) / "data"
    )
    data_root_b = (
        agent_home_dir(stack.home_dir, stack.agent_b_name, tenant_id=stack.tenant_b_id) / "data"
    )
    assert data_root_a.exists(), f"tenant-a data root missing: {data_root_a}"
    assert data_root_b.exists(), f"tenant-b data root missing: {data_root_b}"
    assert data_root_a != data_root_b


# ---------------------------------------------------------------------------
# E2E-1  cross-agent query — zero data bleed
# ---------------------------------------------------------------------------


def test_cross_agent_query_no_data_bleed(
    managed_stack_two_tenants: TwoTenantStack,
) -> None:
    """Write to agent-a's memory; verify agent-b's DB has zero results."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend

    stack = managed_stack_two_tenants
    sentinel_a = f"sentinel-a-{uuid.uuid4()}"
    sentinel_b = f"sentinel-b-{uuid.uuid4()}"

    data_dir_a = (
        agent_home_dir(stack.home_dir, stack.agent_a_name, tenant_id=stack.tenant_a_id) / "data"
    )
    data_dir_b = (
        agent_home_dir(stack.home_dir, stack.agent_b_name, tenant_id=stack.tenant_b_id) / "data"
    )

    backend_a = SQLiteTenantBackend(data_dir=data_dir_a)
    backend_b = SQLiteTenantBackend(data_dir=data_dir_b)

    # Write sentinel to agent-a; verify agent-b sees nothing.
    scope_a = backend_a.resolve_agent(stack.tenant_a_id, stack.agent_a_name)
    am_a = scope_a.open_agent_memory_db(AGENT_STATE_MIGRATIONS)
    with am_a.transaction() as conn:
        conn.execute(
            _INSERT_SQL,
            {
                "id": str(uuid.uuid4()),
                "type": "context",
                "content": sentinel_a,
                "status": "active",
                "source": "e2e-test",
                "source_ref": None,
                "created_by": "e2e",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )

    scope_b = backend_b.resolve_agent(stack.tenant_b_id, stack.agent_b_name)
    am_b = scope_b.open_agent_memory_db(AGENT_STATE_MIGRATIONS)
    with am_b.transaction() as conn:
        rows = conn.execute(
            "SELECT content FROM agent_memory_items WHERE content = :sentinel",
            {"sentinel": sentinel_a},
        ).fetchall()
    assert len(rows) == 0, f"agent-b unexpectedly found agent-a sentinel: {rows}"

    # Reverse: write to agent-b; verify agent-a sees nothing.
    scope_b2 = backend_b.resolve_agent(stack.tenant_b_id, stack.agent_b_name)
    am_b2 = scope_b2.open_agent_memory_db(AGENT_STATE_MIGRATIONS)
    with am_b2.transaction() as conn:
        conn.execute(
            _INSERT_SQL,
            {
                "id": str(uuid.uuid4()),
                "type": "context",
                "content": sentinel_b,
                "status": "active",
                "source": "e2e-test",
                "source_ref": None,
                "created_by": "e2e",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )

    scope_a2 = backend_a.resolve_agent(stack.tenant_a_id, stack.agent_a_name)
    am_a2 = scope_a2.open_agent_memory_db(AGENT_STATE_MIGRATIONS)
    with am_a2.transaction() as conn:
        rows = conn.execute(
            "SELECT content FROM agent_memory_items WHERE content = :sentinel",
            {"sentinel": sentinel_b},
        ).fetchall()
    assert len(rows) == 0, f"agent-a unexpectedly found agent-b sentinel: {rows}"


# ---------------------------------------------------------------------------
# E2E-2  file-level physical isolation
# ---------------------------------------------------------------------------


def test_file_level_physical_isolation(
    managed_stack_two_tenants: TwoTenantStack,
) -> None:
    """SQLite files for each tenant live in disjoint directory trees."""
    stack = managed_stack_two_tenants

    agents_dir_a = agent_home_dir(stack.home_dir, stack.agent_a_name, tenant_id=stack.tenant_a_id)
    agents_dir_b = agent_home_dir(stack.home_dir, stack.agent_b_name, tenant_id=stack.tenant_b_id)

    files_a = {p.resolve() for p in agents_dir_a.rglob("*.db")}
    files_b = {p.resolve() for p in agents_dir_b.rglob("*.db")}

    assert files_a, f"no .db files under agent-a home: {agents_dir_a}"
    assert files_b, f"no .db files under agent-b home: {agents_dir_b}"

    overlap = files_a & files_b
    assert not overlap, f"unexpected shared .db files: {overlap}"

    for f in files_a:
        assert not _is_relative_to(f, agents_dir_b), (
            f"tenant-a file {f} leaked into tenant-b agent dir"
        )
    for f in files_b:
        assert not _is_relative_to(f, agents_dir_a), (
            f"tenant-b file {f} leaked into tenant-a agent dir"
        )

    data_dir_a = agents_dir_a / "data"
    data_dir_b = agents_dir_b / "data"
    assert data_dir_a.exists()
    assert data_dir_b.exists()
    assert not _is_relative_to(data_dir_a, data_dir_b)
    assert not _is_relative_to(data_dir_b, data_dir_a)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
