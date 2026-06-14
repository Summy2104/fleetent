"""Integration tests for the minimal OAuth2 consent flow."""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.connector_management.connector_admin_api as api
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )

    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str = "viewer") -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    return {"Authorization": f"Session {auth.create_session(user.id)}"}, user.id


def test_authorize_returns_url_with_state_and_callback_exchanges_code(client):
    from fleetent.platform.connector_management import external_credential_store, external_service_store

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={
            "authorize": "https://github.example/oauth/authorize",
            "token": "https://github.example/oauth/token",
            "client_id": "cid-123",
            "scopes": ["repo"],
        },
    )
    headers, user_id = _session_header()

    authorize = client.get("/admin/connectors/authorize/github", headers=headers)

    assert authorize.status_code == 200
    authorize_url = authorize.json()["authorize_url"]
    parsed = urlparse(authorize_url)
    params = parse_qs(parsed.query)
    state = params["state"][0]
    assert parsed.scheme == "https"
    assert state

    with respx.mock(assert_all_called=True) as router:
        token_route = router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "token-u1",
                    "refresh_token": "refresh-u1",
                    "expires_in": 3600,
                    "scope": "repo",
                    "token_type": "Bearer",
                },
            )
        )
        callback = client.get(
            f"/admin/connectors/callback/github?state={state}&code=auth-code",
            headers=headers,
        )

    assert callback.status_code == 200
    assert token_route.called
    stored = external_credential_store.get_credential(user_id, "github")
    assert stored is not None
    assert stored["status"] == "authorized"
    assert stored["payload"]["access_token"] == "token-u1"


def test_callback_rejects_state_mismatch_without_exchanging_code(client):
    from fleetent.platform.connector_management import external_credential_store, external_service_store

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={
            "authorize": "https://github.example/oauth/authorize",
            "token": "https://github.example/oauth/token",
            "client_id": "cid-123",
        },
    )
    headers, user_id = _session_header()

    with respx.mock(assert_all_called=False) as router:
        token_route = router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "should-not-happen"})
        )
        callback = client.get(
            "/admin/connectors/callback/github?state=wrong-state&code=auth-code",
            headers=headers,
        )

    assert callback.status_code == 400
    assert token_route.called is False
    assert external_credential_store.get_credential(user_id, "github") is None
