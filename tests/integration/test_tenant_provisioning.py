"""Integration tests for tenant directory provisioning (tenant-first layout).

Verifies that SQLiteTenantBackend provisions tenants/<tenant>/ and
tenants/<tenant>/agents/<agent_id>/data/
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

    assert (tmp_path / "tenants" / "acme").exists(), "tenant_scope must provision tenants/<tenant>/"
    assert (tmp_path / "tenants" / "acme").is_dir()


def test_agent_scope_provisions_agent_directory(tmp_path: Path) -> None:
    """Resolving agent_scope creates tenants/<tenant>/agents/<agent_id>/data/ immediately."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.agent_scope("acme", "bot")

    assert (tmp_path / "tenants" / "acme" / "agents" / "bot" / "data").exists(), (
        "agent_scope must provision tenants/<tenant>/agents/<agent_id>/data/"
    )
    assert (tmp_path / "tenants" / "acme" / "agents" / "bot" / "data").is_dir()


def test_provisioning_is_idempotent(tmp_path: Path) -> None:
    """Calling resolve multiple times for the same tenant must not raise."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.tenant_scope("acme")
    router.tenant_scope("acme")  # second call must be idempotent
    router.agent_scope("acme", "bot")
    router.agent_scope("acme", "bot")

    assert (tmp_path / "tenants" / "acme").is_dir()
    assert (tmp_path / "tenants" / "acme" / "agents" / "bot" / "data").is_dir()


def test_provisioning_different_tenants_independent(tmp_path: Path) -> None:
    """Each tenant gets its own directory; they don't interfere."""
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))

    router.tenant_scope("tenant-1")
    router.tenant_scope("tenant-2")

    assert (tmp_path / "tenants" / "tenant-1").is_dir()
    assert (tmp_path / "tenants" / "tenant-2").is_dir()
    # One tenant's directory must not contain the other's
    assert not (tmp_path / "tenants" / "tenant-1" / "tenant-2").exists()
    assert not (tmp_path / "tenants" / "tenant-2" / "tenant-1").exists()
