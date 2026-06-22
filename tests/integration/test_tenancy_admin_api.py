from __future__ import annotations

from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.user_store as user_store
from fleetent.server import app
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    apply_migrations(db_path)
    return TestClient(app, raise_server_exceptions=True)


def test_tenancy_router_is_registered(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.get("/admin/tenancy/tenants", headers=_session_header("admin"))

    assert response.status_code == 200


def test_create_tenant_success(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/tenancy/tenants",
        headers=_session_header("admin"),
        json={"id": "acme", "name": "Acme"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "acme"


def test_list_tenants(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    tenancy_store.create_tenant(id="acme", name="Acme")

    response = client.get("/admin/tenancy/tenants", headers=_session_header("admin"))

    assert response.status_code == 200
    assert "acme" in {tenant["id"] for tenant in response.json()}


def test_create_team(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/tenancy/teams",
        headers=_session_header("admin"),
        json={"id": "eng", "tenant_id": "default", "name": "Engineering"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "eng"
    assert response.json()["tenant_id"] == "default"


def test_set_user_tenant(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    user, _ = user_store.create_user("Target User")
    tenancy_store.create_tenant(id="acme", name="Acme")

    response = client.post(
        f"/admin/tenancy/users/{user.id}/tenant",
        headers=_session_header("admin"),
        json={"tenant_id": "acme"},
    )

    assert response.status_code == 200
    assert user_store.get_by_id(user.id).tenant_id == "acme"


def test_set_approver(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    approver, _ = user_store.create_user("Approver")

    response = client.patch(
        "/admin/tenancy/approvers/default",
        headers=_session_header("admin"),
        json={"entity_type": "tenant", "approver_user_id": approver.id},
    )

    assert response.status_code == 200
    assert tenancy_store.get_tenant("default")["approver_user_id"] == approver.id


def test_unauthenticated_returns_401(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/admin/tenancy/tenants")

    assert response.status_code == 401


def test_viewer_role_returns_403(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/tenancy/tenants",
        headers=_session_header("viewer"),
        json={"id": "acme", "name": "Acme"},
    )

    assert response.status_code == 403
