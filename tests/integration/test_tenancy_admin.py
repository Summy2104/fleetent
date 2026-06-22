"""Integration tests for tenancy admin provisioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent import user_store
from tests.integration.test_migrations import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


# ── Admin API tests ───────────────────────────────────────────────────────────


def _make_api(monkeypatch: pytest.MonkeyPatch, *, is_admin: bool = True):
    """Return the tenancy admin API module with auth and audit mocked."""
    from fleetent.platform.tenancy import admin_api

    admin_user, _ = user_store.create_user("Admin")
    user_store.set_role(admin_user.id, "admin")

    monkeypatch.setattr(admin_api.auth, "validate_session", lambda token, idle: admin_user.id)
    if not is_admin:
        viewer, _ = user_store.create_user("Viewer")
        monkeypatch.setattr(admin_api.auth, "validate_session", lambda token, idle: viewer.id)

    audits: list[tuple[object, ...]] = []
    monkeypatch.setattr(admin_api.audit_log, "write_audit", lambda *a, **kw: audits.append(a))
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
    user, _ = user_store.create_user("TargetUser")
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
    approver, _ = user_store.create_user("Approver")
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
    approver, _ = user_store.create_user("Approver2")
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
