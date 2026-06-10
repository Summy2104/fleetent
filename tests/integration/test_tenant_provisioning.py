"""Integration tests for tenant directory provisioning (3d task 1.3).

Verifies that SQLiteTenantBackend provisions <tenant>/ and <tenant>/<agent_id>/
directories eagerly at scope-resolution time (not only on first DB write).
This makes provisioning predictable and observable before any DB operation.
"""

from __future__ import annotations

from pathlib import Path

from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def test_tenant_scope_provisions_tenant_directory(tmp_path: Path) -> None:
    """Resolving tenant_scope creates <tenant>/ directory immediately."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.tenant_scope("acme")

    assert (tmp_path / "acme").exists(), "tenant_scope must provision <tenant>/ directory"
    assert (tmp_path / "acme").is_dir()


def test_agent_scope_provisions_agent_directory(tmp_path: Path) -> None:
    """Resolving agent_scope creates <tenant>/<agent_id>/ directory immediately."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.agent_scope("acme", "bot")

    assert (tmp_path / "acme" / "bot").exists(), "agent_scope must provision <tenant>/<agent_id>/"
    assert (tmp_path / "acme" / "bot").is_dir()


def test_provisioning_is_idempotent(tmp_path: Path) -> None:
    """Calling resolve multiple times for the same tenant must not raise."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.tenant_scope("acme")
    router.tenant_scope("acme")  # second call must be idempotent
    router.agent_scope("acme", "bot")
    router.agent_scope("acme", "bot")

    assert (tmp_path / "acme").is_dir()
    assert (tmp_path / "acme" / "bot").is_dir()


def test_provisioning_different_tenants_independent(tmp_path: Path) -> None:
    """Each tenant gets its own directory; they don't interfere."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.tenant_scope("tenant-1")
    router.tenant_scope("tenant-2")

    assert (tmp_path / "tenant-1").is_dir()
    assert (tmp_path / "tenant-2").is_dir()
    # One tenant's directory must not contain the other's
    assert not (tmp_path / "tenant-1" / "tenant-2").exists()
    assert not (tmp_path / "tenant-2" / "tenant-1").exists()
