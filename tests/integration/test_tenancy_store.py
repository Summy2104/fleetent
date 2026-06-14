"""Integration tests for tenancy store — Task 4.1/4.2.

Tests tenancy store CRUD, approver set/get, and user tenant assignment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent import user_store
from tests.integration.test_migrations import apply_migrations


@pytest.fixture(autouse=True)
def _db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")


# ── Task 4.1/4.2: tenancy store CRUD + approver ──────────────────────────────


def test_create_tenant_returns_id(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_tenant

    tenant = create_tenant("t1", "Acme Corp")
    assert tenant["id"] == "t1"
    assert tenant["name"] == "Acme Corp"
    assert tenant["status"] == "active"


def test_get_tenant_returns_created(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_tenant, get_tenant

    create_tenant("t2", "Beta LLC")
    tenant = get_tenant("t2")
    assert tenant is not None
    assert tenant["name"] == "Beta LLC"


def test_get_tenant_returns_none_for_missing(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import get_tenant

    assert get_tenant("nonexistent") is None


def test_default_tenant_exists(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import get_tenant

    tenant = get_tenant("default")
    assert tenant is not None
    assert tenant["id"] == "default"


def test_create_team_returns_id(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_team

    team = create_team("team1", "default", "Engineering")
    assert team["id"] == "team1"
    assert team["tenant_id"] == "default"
    assert team["name"] == "Engineering"


def test_get_team_returns_created(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_team, get_team

    create_team("team2", "default", "Finance")
    team = get_team("team2")
    assert team is not None
    assert team["name"] == "Finance"


def test_approver_is_null_by_default(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import get_tenant

    tenant = get_tenant("default")
    assert tenant is not None
    assert tenant["approver_user_id"] is None


def test_set_tenant_approver(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import get_tenant, set_tenant_approver

    user, _ = user_store.create_user("Approver A")
    set_tenant_approver("default", user.id)
    tenant = get_tenant("default")
    assert tenant is not None
    assert tenant["approver_user_id"] == user.id


def test_set_team_approver(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_team, get_team, set_team_approver

    create_team("team3", "default", "Legal")
    user, _ = user_store.create_user("Approver B")
    set_team_approver("team3", user.id)
    team = get_team("team3")
    assert team is not None
    assert team["approver_user_id"] == user.id


def test_set_tenant_approver_to_none_clears(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import get_tenant, set_tenant_approver

    user, _ = user_store.create_user("Approver C")
    set_tenant_approver("default", user.id)
    set_tenant_approver("default", None)
    tenant = get_tenant("default")
    assert tenant is not None
    assert tenant["approver_user_id"] is None


def test_set_user_tenant(tmp_path: Path) -> None:
    from fleetent.platform.tenancy.store import create_tenant, set_user_tenant

    create_tenant("corp", "Corp Inc")
    user, _ = user_store.create_user("Employee")
    set_user_tenant(user.id, "corp")
    refreshed = user_store.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.tenant_id == "corp"


def test_new_user_has_default_tenant_id(tmp_path: Path) -> None:
    user, _ = user_store.create_user("NewUser")
    assert user.tenant_id == "default"
