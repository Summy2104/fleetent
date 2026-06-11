"""Integration: tenancy.store uses db.py boundary (WAL + db.transaction).

Task 3.1 / 3.2 (retire-raw-sqlite-connect):
- Verifies tenants/teams CRUD and approver operations work after migration.
- Verifies the SQLite connection opens in WAL journal mode.
Uses DATABASE_URL monkeypatch (not DB_PATH) as the isolation mechanism.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    from tests.integration._migration_template import apply_migrations

    p = tmp_path / "management.db"
    apply_migrations(p)
    return p


@pytest.fixture(autouse=True)
def _use_db(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


# ── WAL mode ──────────────────────────────────────────────────────────────────


def test_tenancy_store_connection_uses_wal(db_path: Path) -> None:
    """tenancy.store must open connections with WAL journal mode via db.py."""
    from fleetent.platform.tenancy.store import create_tenant

    create_tenant(name="WAL-check")
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal", f"Expected WAL, got {mode!r}"


# ── CRUD behaviour ────────────────────────────────────────────────────────────


def test_create_tenant_returns_dict() -> None:
    from fleetent.platform.tenancy.store import create_tenant

    t = create_tenant(name="Acme Corp")
    assert t["name"] == "Acme Corp"
    assert t["status"] == "active"


def test_get_tenant_found() -> None:
    from fleetent.platform.tenancy.store import create_tenant, get_tenant

    t = create_tenant(id="t-x1", name="Beta LLC")
    found = get_tenant("t-x1")
    assert found is not None
    assert found["name"] == "Beta LLC"


def test_get_tenant_missing_returns_none() -> None:
    from fleetent.platform.tenancy.store import get_tenant

    assert get_tenant("no-such-id") is None


def test_list_tenants_includes_created() -> None:
    from fleetent.platform.tenancy.store import create_tenant, list_tenants

    create_tenant(id="t-list1", name="Corp A")
    create_tenant(id="t-list2", name="Corp B")
    ids = {t["id"] for t in list_tenants()}
    assert {"t-list1", "t-list2"} <= ids


def test_set_tenant_approver() -> None:
    from fleetent import user_store
    from fleetent.platform.tenancy.store import get_tenant, set_tenant_approver

    user = user_store.create_user("Approver")
    set_tenant_approver("default", user.id)
    t = get_tenant("default")
    assert t is not None
    assert t["approver_user_id"] == user.id


def test_create_team_returns_dict() -> None:
    from fleetent.platform.tenancy.store import create_team

    team = create_team(name="Engineering")
    assert team["name"] == "Engineering"
    assert team["tenant_id"] == "default"


def test_list_teams_for_tenant() -> None:
    from fleetent.platform.tenancy.store import create_team, list_teams

    create_team(id="team-a", name="Alpha")
    create_team(id="team-b", name="Beta")
    ids = {t["id"] for t in list_teams()}
    assert {"team-a", "team-b"} <= ids


def test_set_team_approver() -> None:
    from fleetent import user_store
    from fleetent.platform.tenancy.store import create_team, get_team, set_team_approver

    team = create_team(name="Legal")
    user = user_store.create_user("Team Approver")
    set_team_approver(team["id"], user.id)
    found = get_team(team["id"])
    assert found is not None
    assert found["approver_user_id"] == user.id
