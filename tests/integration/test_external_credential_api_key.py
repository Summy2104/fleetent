"""Integration tests for the api-key credential path (P3 external-credential-api-key).

Covers the user self-submit endpoint (no admin-on-behalf) and the vault provider's
api-key resolution branch (Credential when present, NeedsConsent pointing at the
submit entry when absent, never an OAuth refresh).
"""

from __future__ import annotations

import base64
import json

import pytest
from _pytest.logging import LogCaptureFixture
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.connector_management.connector_admin_api as api
import fleetent.user_store as user_store
from fleetent import connectors, eval_logger
from fleetent.platform.connector_management import (
    external_credential_store,
    external_service_store,
    vault_provider,
)
from fleetent.tools import builtin_tools  # noqa: F401  # load-bearing tool registration
from fleetent.tools import registry as tool_registry
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


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def _add_apikey_service(client, service_id: str = "internal-api") -> None:
    admin_token, _ = _session_for("admin")
    r = client.post(
        "/admin/connectors",
        headers=_hdr(admin_token),
        json={"id": service_id, "display_name": "Internal API", "protocol": "apikey"},
    )
    assert r.status_code == 200, r.text


# --- Task 1: user self-submit flow -------------------------------------------


def test_user_submits_api_key_encrypted_and_authorized(client):
    _add_apikey_service(client)
    token, user_id = _session_for("viewer")

    r = client.post(
        "/admin/connectors/internal-api/credentials",
        headers=_hdr(token),
        json={"api_key": "sk-secret-123"},
    )
    assert r.status_code == 200, r.text

    # Plaintext key must never be echoed back to the caller.
    assert "sk-secret-123" not in r.text

    stored = external_credential_store.get_credential(user_id, "internal-api")
    assert stored is not None
    assert stored["status"] == "authorized"
    assert stored["payload"]["api_key"] == "sk-secret-123"


def test_submitted_api_key_is_ciphertext_at_rest(client, tmp_path):
    _add_apikey_service(client)
    token, user_id = _session_for("viewer")
    client.post(
        "/admin/connectors/internal-api/credentials",
        headers=_hdr(token),
        json={"api_key": "sk-secret-xyz"},
    )

    # The raw ciphertext column must not contain the plaintext key.
    db_path = tmp_path / "users.db"
    raw = db_path.read_bytes()
    assert b"sk-secret-xyz" not in raw


def test_submit_requires_authentication(client):
    _add_apikey_service(client)
    r = client.post(
        "/admin/connectors/internal-api/credentials",
        json={"api_key": "sk-secret-123"},
    )
    assert r.status_code == 401


def test_submit_rejects_unknown_service(client):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/connectors/does-not-exist/credentials",
        headers=_hdr(token),
        json={"api_key": "sk-secret-123"},
    )
    assert r.status_code == 404


def test_submit_rejects_non_apikey_protocol(client):
    admin_token, _ = _session_for("admin")
    client.post(
        "/admin/connectors",
        headers=_hdr(admin_token),
        json={"id": "gh", "display_name": "GitHub", "oauth_config": {"client_id": "cid"}},
    )
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/connectors/gh/credentials",
        headers=_hdr(token),
        json={"api_key": "sk-secret-123"},
    )
    assert r.status_code == 422


def test_no_admin_on_behalf_submit_route(client):
    # There must be no endpoint that accepts a *target* user_id for key submission:
    # the key is always bound to the authenticated session's own user.
    for route in api.router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "credential" in path and "POST" in methods:
            assert "{user_id}" not in path, f"admin-on-behalf submit route exists: {path}"


# --- Task 2: provider resolution of api-key credentials ----------------------


@pytest.fixture
def provider_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )
    return db_path


@pytest.fixture(autouse=True)
def restore_provider():
    before = connectors._provider
    yield
    connectors._provider = before


def test_provider_returns_credential_for_apikey_service(provider_db):
    external_service_store.add_service("internal-api", "Internal API", protocol="apikey")
    external_credential_store.put_apikey_credential("u1", "internal-api", "sk-secret-123")

    result = vault_provider.get_credential("u1", "internal-api", [])

    assert isinstance(result, connectors.Credential)
    assert result.connector == "internal-api"
    assert result.client["api_key"] == "sk-secret-123"


def test_provider_needs_consent_points_at_submit_for_apikey(provider_db):
    external_service_store.add_service("internal-api", "Internal API", protocol="apikey")

    result = vault_provider.get_credential("u1", "internal-api", [])

    assert isinstance(result, connectors.NeedsConsent)
    # The hint must point at the api-key submit entry, not the OAuth authorize jump.
    assert "credentials" in result.consent_url
    assert "authorize" not in result.consent_url


def test_provider_apikey_never_refreshes_even_if_payload_looks_expired(provider_db):
    # An api-key credential has no refresh concept: a stale-looking expires_at must
    # not divert it into the OAuth refresh path. The apikey branch short-circuits first.
    external_service_store.add_service(
        "internal-api",
        "Internal API",
        protocol="apikey",
        oauth_config={"token": "https://internal.example/oauth/token"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "internal-api",
        {"api_key": "sk-secret-123", "expires_at": "2000-01-01T00:00:00+00:00"},
        updated_by="u1",
        status="authorized",
    )

    result = vault_provider.get_credential("u1", "internal-api", [])

    assert isinstance(result, connectors.Credential)
    assert result.client["api_key"] == "sk-secret-123"


def test_dispatch_injects_apikey_client_and_hides_key(provider_db):
    # Reuse the builtin connector tool: a connector named "github" served as apikey.
    external_service_store.add_service("github", "GitHub", protocol="apikey")
    external_credential_store.put_apikey_credential("u1", "github", "sk-very-secret")
    connectors.set_provider(vault_provider.get_credential)

    result = tool_registry.dispatch("github_connection_status", "{}", user_id="u1")

    assert "github credential ready" in result
    assert "sk-very-secret" not in result
    serialized = json.dumps(eval_logger._serialize({"role": "tool", "content": result}))
    assert "sk-very-secret" not in serialized


def test_dispatch_prompts_submit_when_apikey_missing(provider_db):
    external_service_store.add_service("github", "GitHub", protocol="apikey")
    connectors.set_provider(vault_provider.get_credential)

    result = tool_registry.dispatch("github_connection_status", "{}", user_id="u1")

    assert "requires authorization" in result
    assert "credentials" in result


def test_apikey_plaintext_never_in_repr_or_logs(provider_db, caplog: LogCaptureFixture):
    external_service_store.add_service("internal-api", "Internal API", protocol="apikey")
    external_credential_store.put_apikey_credential("u1", "internal-api", "sk-secret-123")

    with caplog.at_level("DEBUG"):
        result = vault_provider.get_credential("u1", "internal-api", [])

    assert isinstance(result, connectors.Credential)
    rendered = f"{result!r} {result!s} {caplog.text}"
    assert "sk-secret-123" not in rendered
