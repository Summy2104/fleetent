"""Integration: tenancy.store uses db.py boundary (WAL + db.transaction).

Task 3.1 / 3.2 (retire-raw-sqlite-connect):
- Verifies tenants/teams CRUD and approver operations work after migration.
- Verifies the SQLite connection opens in WAL journal mode.
Uses DATABASE_URL monkeypatch (not DB_PATH) as the isolation mechanism.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
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


def test_db_runtime_enables_foreign_keys_and_rejects_orphan_agent(db_path: Path) -> None:
    from fleetent.config import Settings
    from fleetent.db import create_database

    database = create_database(Settings().database_url)
    pragma = database.execute("PRAGMA foreign_keys").fetchone()
    assert pragma is not None
    assert int(pragma["foreign_keys"]) == 1

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as conn:
        conn.execute(
            "INSERT INTO agents "
            "(name, system_prompt, allowed_tools, features, plugins, allowed_skills, "
            "created_at, tenant_id, team_id, icon, config_overrides) "
            "VALUES "
            "(:name, :system_prompt, :allowed_tools, :features, :plugins, :allowed_skills, "
            ":created_at, :tenant_id, :team_id, :icon, :config_overrides)",
            {
                "name": "orphan-agent",
                "system_prompt": "prompt",
                "allowed_tools": "[]",
                "features": "{}",
                "plugins": "[]",
                "allowed_skills": "[]",
                "created_at": datetime.now(UTC).isoformat(),
                "tenant_id": "missing-tenant",
                "team_id": None,
                "icon": None,
                "config_overrides": "{}",
            },
        )

    row = database.execute(
        "SELECT COUNT(*) AS c FROM agents WHERE name = :name",
        {"name": "orphan-agent"},
    ).fetchone()
    assert row is not None and int(row["c"]) == 0


# ── CRUD behaviour ────────────────────────────────────────────────────────────


def test_create_tenant_returns_dict() -> None:
    from fleetent.platform.tenancy.store import create_tenant

    t = create_tenant(name="Acme Corp")
    assert t["name"] == "Acme Corp"
    assert t["status"] == "active"


def test_get_tenant_found() -> None:
    from fleetent.platform.tenancy.store import create_tenant, get_tenant

    create_tenant(id="t-x1", name="Beta LLC")
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
