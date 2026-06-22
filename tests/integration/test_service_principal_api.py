from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.user_management.user_admin_api as api
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def test_create_service_principal_returns_key_once(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/service-principals",
        headers=_session_header("admin"),
        json={"name": "ops-bot"},
    )

    assert response.status_code == 201


def test_rotate_key_revokes_and_issues(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    user, old_key = user_store.create_user("Rotate Me")

    response = client.post(
        f"/admin/users/{user.id}/rotate-key",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["api_key_plaintext_once"].startswith("ma-")
    assert body["api_key_plaintext_once"] != old_key
    keys = client.get(f"/admin/users/{user.id}/keys", headers=_session_header("admin")).json()
    assert all("plaintext" not in key for key in keys)


def test_rotate_unknown_user_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/users/00000000-0000-0000-0000-000000000000/rotate-key",
        headers=_session_header("admin"),
    )

    assert response.status_code == 404


def test_non_admin_403(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/service-principals",
        headers=_session_header("viewer"),
        json={"name": "ops-bot"},
    )

    assert response.status_code == 403
