"""Integration tests for the user↔IM relationship workbench.

Covers the new identity-mapping store helpers (`list_mappings` / `create_mapping`)
and the `/admin/im-identities` admin API (list with user info, create, delete, authz).
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im
from fleetent.server import app
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'management.db'}")
    apply_migrations(tmp_path / "management.db")
    return tmp_path / "management.db"


# --- store layer -----------------------------------------------------------


def test_list_mappings_carries_user_name_and_email(db):
    user, _ = user_store.create_user(name="Alice", email="alice@example.com", tenant_id="default")
    im.create_mapping("slack", "U1", user.id, actor="admin1")

    rows = im.list_mappings()

    assert len(rows) == 1
    row = rows[0]
    assert row["platform"] == "slack"
    assert row["platform_user_id"] == "U1"
    assert row["user_id"] == user.id
    assert row["user_name"] == "Alice"
    assert row["user_email"] == "alice@example.com"


def test_create_mapping_persists_and_audits(db):
    user, _ = user_store.create_user(name="Bob", tenant_id="default")

    created = im.create_mapping("telegram", "T1", user.id, actor="admin1")

    assert created["platform"] == "telegram"
    assert created["platform_user_id"] == "T1"
    assert created["user_id"] == user.id
    assert created["user_name"] == "Bob"
    assert isinstance(created["id"], int)
    assert im.get_mapped_user("telegram", "T1").id == user.id
    assert len(audit.search_audit(action="create_im_user", target_id="telegram:T1")) == 1


def test_create_mapping_missing_user_raises(db):
    with pytest.raises(ValueError, match="target user not found"):
        im.create_mapping("slack", "U9", "nonexistent-user-id")


def test_create_mapping_duplicate_handle_raises(db):
    user, _ = user_store.create_user(name="Carol", tenant_id="default")
    im.create_mapping("slack", "U2", user.id)

    with pytest.raises(ValueError, match="already exists"):
        im.create_mapping("slack", "U2", user.id)


# --- admin API -------------------------------------------------------------


@pytest.fixture
def client(db, monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(name=f"{role}-actor")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def _seed_user(name: str, email: str | None = None) -> str:
    user, _ = user_store.create_user(name=name, email=email, tenant_id="default")
    return user.id


def test_api_list_mappings_returns_user_info(client):
    uid = _seed_user("Dana", "dana@example.com")
    im.create_mapping("slack", "U10", uid)

    response = client.get("/admin/im-identities", headers=_session_header("admin"))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform"] == "slack"
    assert body[0]["platform_user_id"] == "U10"
    assert body[0]["user_id"] == uid
    assert body[0]["user_name"] == "Dana"
    assert body[0]["user_email"] == "dana@example.com"


def test_api_list_mappings_allows_viewer(client):
    response = client.get("/admin/im-identities", headers=_session_header("viewer"))
    assert response.status_code == 200
    assert response.json() == []


def test_api_list_mappings_requires_auth(client):
    response = client.get("/admin/im-identities")
    assert response.status_code == 401


def test_api_create_mapping_success(client):
    uid = _seed_user("Eli")

    response = client.post(
        "/admin/im-identities",
        headers=_session_header("admin"),
        json={"platform": "telegram", "platform_user_id": "T10", "user_id": uid},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "telegram"
    assert body["platform_user_id"] == "T10"
    assert body["user_id"] == uid
    assert body["user_name"] == "Eli"
    assert im.get_mapped_user("telegram", "T10").id == uid


def test_api_create_mapping_missing_user_returns_404(client):
    response = client.post(
        "/admin/im-identities",
        headers=_session_header("admin"),
        json={"platform": "slack", "platform_user_id": "U11", "user_id": "ghost"},
    )
    assert response.status_code == 404


def test_api_create_mapping_duplicate_returns_409(client):
    uid = _seed_user("Fay")
    payload = {"platform": "slack", "platform_user_id": "U12", "user_id": uid}
    first = client.post("/admin/im-identities", headers=_session_header("admin"), json=payload)
    assert first.status_code == 201

    second = client.post("/admin/im-identities", headers=_session_header("admin"), json=payload)
    assert second.status_code == 409


def test_api_create_mapping_requires_admin(client):
    uid = _seed_user("Gus")
    response = client.post(
        "/admin/im-identities",
        headers=_session_header("viewer"),
        json={"platform": "slack", "platform_user_id": "U13", "user_id": uid},
    )
    assert response.status_code == 403


def test_api_delete_mapping_success(client):
    uid = _seed_user("Hana")
    created = im.create_mapping("slack", "U14", uid)

    response = client.delete(
        f"/admin/im-identities/{created['id']}", headers=_session_header("admin")
    )

    assert response.status_code == 204
    assert im.get_mapped_user("slack", "U14") is None


def test_api_delete_mapping_missing_returns_404(client):
    response = client.delete("/admin/im-identities/9999", headers=_session_header("admin"))
    assert response.status_code == 404


def test_api_delete_mapping_requires_admin(client):
    uid = _seed_user("Ivy")
    created = im.create_mapping("slack", "U15", uid)

    response = client.delete(
        f"/admin/im-identities/{created['id']}", headers=_session_header("viewer")
    )

    assert response.status_code == 403
    assert im.get_mapped_user("slack", "U15").id == uid
