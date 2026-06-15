"""Integration tests for multi-provider adapter wiring (Tasks 2.1 + 3.1).

Tests that consent flow (authorize URL + token exchange) is routed through
per-service adapters. External HTTP mocked with respx.
"""

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
import fleetent.platform.connector_management.service_providers as _sp_module
import fleetent.user_store as user_store
from fleetent.platform.connector_management import (
    external_credential_store,
    external_service_store,
)
from tests.integration._migration_template import apply_migrations

_FERNET_KEY = base64.urlsafe_b64encode(b"0" * 32).decode("ascii")


@pytest.fixture()
def vault_db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", _FERNET_KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture()
def client(vault_db):
    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    async def _fake_probe(server_id: str) -> dict:
        return {"connected": True, "tool_count": 0, "tools": []}

    monkeypatch_api = api
    monkeypatch_api.mcp_sync_server = _noop_sync
    monkeypatch_api.mcp_probe = _fake_probe

    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def restore_provider_registry():
    before = dict(_sp_module._REGISTRY)
    yield
    _sp_module._REGISTRY.clear()
    _sp_module._REGISTRY.update(before)


def _session_header(role: str = "viewer") -> tuple[dict[str, str], str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return {"Authorization": f"Session {auth.create_session(u.id)}"}, u.id


def _add_service(service_id: str, name: str, oauth_config: dict) -> None:
    external_service_store.add_service(service_id, name, oauth_config=oauth_config)


# ---------------------------------------------------------------------------
# 2.1 google-drive: authorize URL has offline params; token exchange wired
# ---------------------------------------------------------------------------

_GD_OAUTH_CONFIG = {
    "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
    "token": "https://oauth2.googleapis.com/token",
    "client_id": "gd-client-id",
    "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
}

_GH_OAUTH_CONFIG = {
    "authorize": "https://github.com/login/oauth/authorize",
    "token": "https://github.com/login/oauth/access_token",
    "client_id": "gh-client-id",
    "scopes": ["repo"],
}


def test_google_drive_authorize_url_has_offline_and_consent(client, vault_db):
    _add_service("google-drive", "Google Drive", _GD_OAUTH_CONFIG)
    headers, _ = _session_header()
    r = client.get("/admin/connectors/authorize/google-drive", headers=headers)
    assert r.status_code == 200
    params = parse_qs(urlparse(r.json()["authorize_url"]).query)
    assert params.get("access_type") == ["offline"]
    assert params.get("prompt") == ["consent"]
    assert "state" in params


def test_github_authorize_url_has_no_offline_param(client, vault_db):
    _add_service("github", "GitHub", _GH_OAUTH_CONFIG)
    headers, _ = _session_header()
    r = client.get("/admin/connectors/authorize/github", headers=headers)
    assert r.status_code == 200
    params = parse_qs(urlparse(r.json()["authorize_url"]).query)
    assert "access_type" not in params
    assert "state" in params


def test_google_drive_token_exchange_includes_client_secret(client, vault_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "gd-secret")
    _add_service("google-drive", "Google Drive", _GD_OAUTH_CONFIG)
    headers, user_id = _session_header()

    r_auth = client.get("/admin/connectors/authorize/google-drive", headers=headers)
    state = parse_qs(urlparse(r_auth.json()["authorize_url"]).query)["state"][0]

    with respx.mock(assert_all_called=True) as router:
        token_route = router.post("https://oauth2.googleapis.com/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "gd-access",
                    "refresh_token": "gd-refresh",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/drive.readonly",
                    "token_type": "Bearer",
                },
            )
        )
        callback = client.get(
            f"/admin/connectors/callback/google-drive?state={state}&code=gd-code",
            headers=headers,
        )

    assert callback.status_code == 200
    assert token_route.called
    # Verify client_secret was sent in the POST body
    body = parse_qs(token_route.calls[0].request.content.decode())
    assert body.get("client_secret") == ["gd-secret"]
    assert body.get("code") == ["gd-code"]

    stored = external_credential_store.get_credential(user_id, "google-drive")
    assert stored is not None
    assert stored["status"] == "authorized"
    assert stored["payload"]["access_token"] == "gd-access"


def test_github_token_exchange_without_client_secret(client, vault_db):
    # No GITHUB_CLIENT_SECRET env var set → client_secret omitted from request
    _add_service("github", "GitHub", _GH_OAUTH_CONFIG)
    headers, user_id = _session_header()

    r_auth = client.get("/admin/connectors/authorize/github", headers=headers)
    state = parse_qs(urlparse(r_auth.json()["authorize_url"]).query)["state"][0]

    with respx.mock(assert_all_called=True) as router:
        token_route = router.post("https://github.com/login/oauth/access_token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "gh-access",
                    "scope": "repo",
                    "token_type": "bearer",
                },
            )
        )
        callback = client.get(
            f"/admin/connectors/callback/github?state={state}&code=gh-code",
            headers=headers,
        )

    assert callback.status_code == 200
    body = parse_qs(token_route.calls[0].request.content.decode())
    assert "client_secret" not in body  # empty string → not included

    stored = external_credential_store.get_credential(user_id, "github")
    assert stored is not None
    assert stored["payload"]["access_token"] == "gh-access"


def test_two_services_credentials_stored_independently(client, vault_db, monkeypatch):
    """google-drive and github credentials coexist without interference."""
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "gd-s")
    _add_service("google-drive", "Google Drive", _GD_OAUTH_CONFIG)
    _add_service("github", "GitHub", _GH_OAUTH_CONFIG)
    headers, user_id = _session_header()

    # Authorize google-drive
    r = client.get("/admin/connectors/authorize/google-drive", headers=headers)
    state_gd = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    with respx.mock() as mock_gd:
        mock_gd.post("https://oauth2.googleapis.com/token").mock(
            return_value=httpx.Response(200, json={"access_token": "gd-tok", "expires_in": 3600})
        )
        client.get(
            f"/admin/connectors/callback/google-drive?state={state_gd}&code=gd-c",
            headers=headers,
        )

    # Authorize github (same user)
    r = client.get("/admin/connectors/authorize/github", headers=headers)
    state_gh = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    with respx.mock() as mock_gh:
        mock_gh.post("https://github.com/login/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "gh-tok"})
        )
        client.get(
            f"/admin/connectors/callback/github?state={state_gh}&code=gh-c",
            headers=headers,
        )

    gd = external_credential_store.get_credential(user_id, "google-drive")
    gh = external_credential_store.get_credential(user_id, "github")
    assert gd is not None and gd["payload"]["access_token"] == "gd-tok"
    assert gh is not None and gh["payload"]["access_token"] == "gh-tok"
    # Credentials are separate rows
    assert gd["payload"]["access_token"] != gh["payload"]["access_token"]


# ---------------------------------------------------------------------------
# 3.1 new service without changing core dispatch/consent code
# ---------------------------------------------------------------------------


def test_new_service_via_register_and_service_row_only(client, vault_db, monkeypatch):
    """Registering adapter + adding service row → consent works, no core changes."""
    from fleetent.platform.connector_management.service_providers import (
        _GenericOAuth2Provider,
        register_provider,
    )

    # One-line adapter registration (in practice done at startup or in a plugin)
    register_provider("acme-crm", _GenericOAuth2Provider())

    # One-row service registration via admin API
    admin_headers, _ = _session_header("admin")
    r = client.post(
        "/admin/connectors",
        headers=admin_headers,
        json={
            "id": "acme-crm",
            "display_name": "Acme CRM",
            "oauth_config": {
                "authorize": "https://acme.example/oauth/authorize",
                "token": "https://acme.example/oauth/token",
                "client_id": "acme-client-id",
            },
        },
    )
    assert r.status_code == 200

    # Consent flow works without touching dispatch/consent core
    user_headers, user_id = _session_header("viewer")
    r_auth = client.get("/admin/connectors/authorize/acme-crm", headers=user_headers)
    assert r_auth.status_code == 200
    params = parse_qs(urlparse(r_auth.json()["authorize_url"]).query)
    assert "state" in params
    assert params.get("client_id") == ["acme-client-id"]

    state = params["state"][0]
    with respx.mock(assert_all_called=True) as mock_acme:
        mock_acme.post("https://acme.example/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "acme-tok", "expires_in": 3600})
        )
        callback = client.get(
            f"/admin/connectors/callback/acme-crm?state={state}&code=acme-code",
            headers=user_headers,
        )

    assert callback.status_code == 200
    stored = external_credential_store.get_credential(user_id, "acme-crm")
    assert stored is not None
    assert stored["payload"]["access_token"] == "acme-tok"


def test_refresh_token_request_includes_client_secret_from_env(vault_db, monkeypatch):
    """vault_provider._refresh_tokens sends client_secret read from env (P2 compat)."""
    from datetime import UTC, datetime, timedelta

    import fleetent.platform.connector_management.vault_provider as vp
    from fleetent import connectors

    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-refresh-secret")
    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={
            "token": "https://github.example/oauth/token",
            "client_id": "cid-123",
        },
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "expired",
            "refresh_token": "ref-tok",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        token_route = router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "fresh", "refresh_token": "ref2", "expires_in": 3600},
            )
        )
        result = vp.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.Credential)
    body = parse_qs(token_route.calls[0].request.content.decode())
    assert body.get("client_secret") == ["gh-refresh-secret"]
    assert body.get("grant_type") == ["refresh_token"]
