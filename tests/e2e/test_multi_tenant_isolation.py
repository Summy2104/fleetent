"""E2E: multi-tenant data isolation in the managed stack.

Verifies that two tenants running on the same node have:
1. Separate per-tenant data root directories.
2. Zero cross-tenant data bleed via the shared-memory read path.
3. Physically disjoint SQLite files (file-level isolation).

Lane: slow/nightly — runs under ``make test-e2e``, NOT in ``make test-pr``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from tests.e2e._tenant_helpers import TwoTenantStack

pytest_plugins = ["tests.e2e._tenant_helpers"]

_INSERT_SQL = (
    "INSERT INTO shared_memory_items "
    "(id, scope_type, scope_id, type, content, status, source, created_by, created_at, updated_at)"
    " VALUES"
    " (:id, :scope_type, :scope_id, :type, :content, :status, :source,"
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

    data_root_a = stack.home_dir / "agents" / stack.agent_a_name / "data" / stack.tenant_a_id
    data_root_b = stack.home_dir / "agents" / stack.agent_b_name / "data" / stack.tenant_b_id
    assert data_root_a.exists(), f"tenant-a data root missing: {data_root_a}"
    assert data_root_b.exists(), f"tenant-b data root missing: {data_root_b}"
    assert data_root_a != data_root_b


# ---------------------------------------------------------------------------
# E2E-1  cross-tenant query — zero data bleed
# ---------------------------------------------------------------------------


def test_cross_tenant_query_no_data_bleed(
    managed_stack_two_tenants: TwoTenantStack,
) -> None:
    """Write to tenant-a's shared_memory; verify tenant-b's scope has zero results."""
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend

    stack = managed_stack_two_tenants
    sentinel_a = f"sentinel-a-{uuid.uuid4()}"
    sentinel_b = f"sentinel-b-{uuid.uuid4()}"

    data_dir_a = stack.home_dir / "agents" / stack.agent_a_name / "data"
    data_dir_b = stack.home_dir / "agents" / stack.agent_b_name / "data"

    backend_a = SQLiteTenantBackend(data_dir=data_dir_a)
    backend_b = SQLiteTenantBackend(data_dir=data_dir_b)

    # Write sentinel to tenant-a; verify tenant-b sees nothing.
    scope_a = backend_a.resolve(stack.tenant_a_id)
    sm_a = scope_a.open_shared_memory_db(MIGRATIONS)
    with sm_a.transaction() as conn:
        conn.execute(
            _INSERT_SQL,
            {
                "id": str(uuid.uuid4()),
                "scope_type": "agent",
                "scope_id": stack.agent_a_name,
                "type": "fact",
                "content": sentinel_a,
                "status": "active",
                "source": "e2e-test",
                "created_by": "e2e",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )

    scope_b = backend_b.resolve(stack.tenant_b_id)
    sm_b = scope_b.open_shared_memory_db(MIGRATIONS)
    with sm_b.transaction() as conn:
        rows = conn.execute(
            "SELECT content FROM shared_memory_items WHERE content = :sentinel",
            {"sentinel": sentinel_a},
        ).fetchall()
    assert len(rows) == 0, f"tenant-b unexpectedly found tenant-a sentinel: {rows}"

    # Reverse: write to tenant-b; verify tenant-a sees nothing.
    scope_b2 = backend_b.resolve(stack.tenant_b_id)
    sm_b2 = scope_b2.open_shared_memory_db(MIGRATIONS)
    with sm_b2.transaction() as conn:
        conn.execute(
            _INSERT_SQL,
            {
                "id": str(uuid.uuid4()),
                "scope_type": "agent",
                "scope_id": stack.agent_b_name,
                "type": "fact",
                "content": sentinel_b,
                "status": "active",
                "source": "e2e-test",
                "created_by": "e2e",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )

    scope_a2 = backend_a.resolve(stack.tenant_a_id)
    sm_a2 = scope_a2.open_shared_memory_db(MIGRATIONS)
    with sm_a2.transaction() as conn:
        rows = conn.execute(
            "SELECT content FROM shared_memory_items WHERE content = :sentinel",
            {"sentinel": sentinel_b},
        ).fetchall()
    assert len(rows) == 0, f"tenant-a unexpectedly found tenant-b sentinel: {rows}"


# ---------------------------------------------------------------------------
# E2E-2  file-level physical isolation
# ---------------------------------------------------------------------------


def test_file_level_physical_isolation(
    managed_stack_two_tenants: TwoTenantStack,
) -> None:
    """SQLite files for each tenant live in disjoint directory trees."""
    stack = managed_stack_two_tenants

    agents_dir_a = stack.home_dir / "agents" / stack.agent_a_name
    agents_dir_b = stack.home_dir / "agents" / stack.agent_b_name

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

    tenant_dir_a = stack.home_dir / "agents" / stack.agent_a_name / "data" / stack.tenant_a_id
    tenant_dir_b = stack.home_dir / "agents" / stack.agent_b_name / "data" / stack.tenant_b_id
    assert tenant_dir_a.exists()
    assert tenant_dir_b.exists()
    assert not _is_relative_to(tenant_dir_a, tenant_dir_b)
    assert not _is_relative_to(tenant_dir_b, tenant_dir_a)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
