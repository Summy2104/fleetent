"""Integration tests for tenancy admin provisioning — Task 5.1/5.2.

Tests both the admin CLI commands and the REST API for tenant/team provisioning.
Verifies admin auth guard and audit log writes.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from fleetent import user_store
from fleetent.platform.admin_cli.main import main as admin_cli_main
from tests.integration.test_migrations import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def run_admin(*args: str) -> tuple[str, str, int]:
    """Run admin CLI and return (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent-admin", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin_cli_main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


# ── Admin CLI tests ───────────────────────────────────────────────────────────


def test_create_tenant_cli(tmp_path: Path) -> None:
    stdout, stderr, code = run_admin("create-tenant", "--id", "acme", "--name", "Acme Corp")
    assert code == 0, stderr
    assert "acme" in stdout or "Acme" in stdout


def test_create_tenant_cli_generates_uuid_without_id(tmp_path: Path) -> None:
    stdout, stderr, code = run_admin("create-tenant", "--name", "Auto ID Corp")
    assert code == 0, stderr


def test_create_team_cli(tmp_path: Path) -> None:
    run_admin("create-tenant", "--id", "t1", "--name", "Tenant One")
    stdout, stderr, code = run_admin(
        "create-team", "--id", "eng", "--tenant-id", "t1", "--name", "Engineering"
    )
    assert code == 0, stderr
    assert "eng" in stdout or "Engineering" in stdout


def test_list_tenants_cli(tmp_path: Path) -> None:
    run_admin("create-tenant", "--id", "listed", "--name", "Listed Corp")
    stdout, _, code = run_admin("list-tenants")
    assert code == 0
    assert "listed" in stdout


def test_set_user_tenant_cli(tmp_path: Path) -> None:
    user = user_store.create_user("Test User")
    run_admin("create-tenant", "--id", "corp2", "--name", "Corp Two")
    stdout, stderr, code = run_admin(
        "set-user-tenant", "--user-id", user.id, "--tenant-id", "corp2"
    )
    assert code == 0, stderr
    refreshed = user_store.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.tenant_id == "corp2"


def test_set_tenant_approver_cli(tmp_path: Path) -> None:
    approver = user_store.create_user("Approver User")
    stdout, stderr, code = run_admin(
        "set-approver", "--type", "tenant", "--id", "default", "--user-id", approver.id
    )
    assert code == 0, stderr
    from fleetent.platform.tenancy.store import get_tenant
    tenant = get_tenant("default")
    assert tenant is not None
    assert tenant["approver_user_id"] == approver.id


def test_set_team_approver_cli(tmp_path: Path) -> None:
    run_admin("create-tenant", "--id", "t3", "--name", "T3")
    run_admin("create-team", "--id", "team3", "--tenant-id", "t3", "--name", "Team Three")
    approver = user_store.create_user("Team Approver")
    stdout, stderr, code = run_admin(
        "set-approver", "--type", "team", "--id", "team3", "--user-id", approver.id
    )
    assert code == 0, stderr
    from fleetent.platform.tenancy.store import get_team
    team = get_team("team3")
    assert team is not None
    assert team["approver_user_id"] == approver.id


# ── Admin API tests ───────────────────────────────────────────────────────────


def _make_api(monkeypatch: pytest.MonkeyPatch, *, is_admin: bool = True):
    """Return the tenancy admin API module with auth and audit mocked."""
    from fleetent.platform.tenancy import admin_api

    admin_user = user_store.create_user("Admin")
    user_store.set_role(admin_user.id, "admin")

    monkeypatch.setattr(admin_api.auth, "validate_session", lambda token, idle: admin_user.id)
    if not is_admin:
        viewer = user_store.create_user("Viewer")
        monkeypatch.setattr(admin_api.auth, "validate_session", lambda token, idle: viewer.id)

    audits: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        admin_api.audit_log, "write_audit", lambda *a, **kw: audits.append(a)
    )
    return admin_api, "Session token", audits


def test_api_create_tenant_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    admin_api, auth_header, _ = _make_api(monkeypatch, is_admin=False)
    with pytest.raises(HTTPException) as exc_info:
        admin_api.api_create_tenant(
            admin_api.CreateTenantBody(name="Corp"),
            authorization=auth_header,
        )
    assert exc_info.value.status_code == 403


def test_api_create_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_api, auth_header, audits = _make_api(monkeypatch)
    result = admin_api.api_create_tenant(
        admin_api.CreateTenantBody(name="New Tenant"),
        authorization=auth_header,
    )
    assert result["name"] == "New Tenant"
    assert len(audits) == 1
    assert audits[0][1] == "tenant.create"


def test_api_create_team(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_api, auth_header, audits = _make_api(monkeypatch)
    result = admin_api.api_create_team(
        admin_api.CreateTeamBody(tenant_id="default", name="Finance Team"),
        authorization=auth_header,
    )
    assert result["name"] == "Finance Team"
    assert result["tenant_id"] == "default"
    assert len(audits) == 1
    assert audits[0][1] == "team.create"


def test_api_set_user_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_api, auth_header, audits = _make_api(monkeypatch)
    user = user_store.create_user("TargetUser")
    result = admin_api.api_set_user_tenant(
        user.id,
        admin_api.SetUserTenantBody(tenant_id="default"),
        authorization=auth_header,
    )
    assert result["status"] == "ok"
    assert len(audits) == 1
    assert audits[0][1] == "user.set_tenant"


def test_api_set_tenant_approver(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_api, auth_header, audits = _make_api(monkeypatch)
    approver = user_store.create_user("Approver")
    result = admin_api.api_set_approver(
        "default",
        admin_api.SetApproverBody(approver_user_id=approver.id, entity_type="tenant"),
        authorization=auth_header,
    )
    assert result["status"] == "ok"
    assert len(audits) == 1
    assert audits[0][1] == "tenant.set_approver"


def test_api_set_team_approver(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.platform.tenancy.store import create_team

    admin_api, auth_header, audits = _make_api(monkeypatch)
    create_team("team_x", "default", "Team X")
    approver = user_store.create_user("Approver2")
    result = admin_api.api_set_approver(
        "team_x",
        admin_api.SetApproverBody(approver_user_id=approver.id, entity_type="team"),
        authorization=auth_header,
    )
    assert result["status"] == "ok"
    assert audits[0][1] == "team.set_approver"


def test_api_create_tenant_non_admin_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    admin_api, _, _ = _make_api(monkeypatch, is_admin=False)
    with pytest.raises(HTTPException) as exc_info:
        admin_api.api_create_team(
            admin_api.CreateTeamBody(tenant_id="default", name="X"),
            authorization="Session token",
        )
    assert exc_info.value.status_code == 403
