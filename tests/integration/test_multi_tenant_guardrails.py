"""Dependency guardrail tests for multi-tenant fan-out and read-only projection.

Verifies the three invariants from 3d spec:
1. platform → read-only agent (allowed): platform can open agent DBs read-only
2. agent ✗→ platform (forbidden): agent runtime modules must not import platform
3. No materialized copies: read_projection never writes to platform tables
4. Physical isolation: T1 agent paths don't overlap with T2 agent paths
"""

from __future__ import annotations

from pathlib import Path

# ── Guardrail 1: platform can read agent DBs read-only (direction allowed) ────


def test_platform_read_projection_uses_readonly_connections(tmp_path: Path) -> None:
    """read_projection module only calls open_state_db_ro/open_*_db_ro, never open_state_db."""
    # Verify the module text — any call to open_state_db (without _ro) from read_projection
    # would be a violation (migrate-on-open would run).
    import ast
    import inspect

    from fleetent.platform import read_projection

    source = inspect.getsource(read_projection)
    tree = ast.parse(source)

    # Collect all attribute accesses in the module
    attr_calls = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    ]

    # Must use _ro variants, not the migrate-on-open originals
    assert "open_state_db_ro" in attr_calls, "read_projection must call open_state_db_ro"
    # open_agent_memory_db_ro retired: agent_memory_items now live in agent_state.db
    assert "open_agent_memory_db_ro" not in attr_calls, (
        "read_projection must NOT call open_agent_memory_db_ro — agent_memory_items "
        "now live in agent_state.db; use open_state_db_ro"
    )

    # Must NOT call the write-side open (which would trigger migrations)
    forbidden = {"open_state_db", "open_kb_db", "open_agent_memory_db"}
    used_forbidden = forbidden & set(attr_calls)
    assert not used_forbidden, (
        f"read_projection must not call migrate-on-open functions: {used_forbidden}"
    )


# ── Guardrail 2: agent runtime modules must not import platform ────────────────


_AGENT_RUNTIME_PKGS = [
    "fleetent.runtime",
    "fleetent.session",
    "fleetent.im_gateway",
    "fleetent.tools",
    "fleetent.integrations",
    "fleetent.model",
    "fleetent.observability",
    "fleetent.governance",
    "fleetent.memory",
    "fleetent.long_term_ctx",
    "fleetent.reflection",
]


def _iter_module_sources(pkg_name: str) -> list[tuple[str, str]]:
    """Return (module_name, source_path) for all .py files in a package."""
    import importlib.util

    spec = importlib.util.find_spec(pkg_name)
    if spec is None or spec.submodule_search_locations is None:
        return []
    results = []
    for loc in spec.submodule_search_locations:
        for path in Path(loc).rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            results.append((pkg_name, str(path)))
    return results


def test_agent_runtime_modules_do_not_import_platform() -> None:
    """No agent-runtime module may import from fleetent.platform.*."""
    violations: list[str] = []

    for pkg in _AGENT_RUNTIME_PKGS:
        for _, src_path in _iter_module_sources(pkg):
            content = Path(src_path).read_text(errors="replace")
            if "fleetent.platform" in content:
                violations.append(f"{src_path}: imports fleetent.platform.*")

    assert not violations, "Agent runtime modules must not import fleetent.platform:\n" + "\n".join(
        violations
    )


# ── Guardrail 3: read_projection has no write SQL ──────────────────────────────


def test_read_projection_contains_no_write_sql() -> None:
    """read_projection.py must not contain INSERT/UPDATE/DELETE statements."""
    import inspect

    from fleetent.platform import read_projection

    source = inspect.getsource(read_projection)

    for forbidden in ("INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in source.upper(), (
            f"read_projection must not contain {forbidden!r} SQL — "
            "platform projection must never write to agent databases"
        )


# ── Guardrail 4: physical cross-tenant isolation ──────────────────────────────


def test_different_tenants_have_non_overlapping_paths(tmp_path: Path) -> None:
    """T1 and T2 agent paths are physically disjoint."""
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    t1_agent = router.agent_scope("tenant-1", "bot")
    t2_agent = router.agent_scope("tenant-2", "bot")

    t1_path = t1_agent.state_db.path
    t2_path = t2_agent.state_db.path

    # Paths must be completely disjoint
    assert not t1_path.is_relative_to(tmp_path / "tenants" / "tenant-2"), (
        "T1 agent path must not be inside T2 directory"
    )
    assert not t2_path.is_relative_to(tmp_path / "tenants" / "tenant-1"), (
        "T2 agent path must not be inside T1 directory"
    )

    # Confirm T1 path is under tenant-1/ and T2 under tenant-2/
    assert t1_path.is_relative_to(tmp_path / "tenants" / "tenant-1")
    assert t2_path.is_relative_to(tmp_path / "tenants" / "tenant-2")
