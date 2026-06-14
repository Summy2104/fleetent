"""Integration tests for the vault credential provider and platform seam wiring."""

from __future__ import annotations

import base64
import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
import respx
from _pytest.logging import LogCaptureFixture
from fastapi.testclient import TestClient

from fleetent import connectors
from fleetent.server import app
from tests.integration._migration_template import apply_migrations


def _provider_module():
    spec = importlib.util.find_spec("fleetent.platform.connector_management.vault_provider")
    assert spec is not None, "vault_provider module is missing"
    return importlib.import_module("fleetent.platform.connector_management.vault_provider")


@pytest.fixture(autouse=True)
def restore_provider():
    before = connectors._provider
    yield
    connectors._provider = before


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


def test_vault_provider_returns_credential_for_authorized_user(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service("github", "GitHub")
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {"access_token": "token-u1", "scopes": ["repo"]},
        updated_by="u1",
    )

    result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.Credential)
    assert result.connector == "github"
    assert result.client["access_token"] == "token-u1"


def test_vault_provider_returns_needs_consent_when_missing(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import external_service_store

    external_service_store.add_service("github", "GitHub")

    result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.NeedsConsent)
    assert result.connector == "github"


def test_platform_lifespan_injects_provider_but_standalone_seam_stays_default(provider_db):
    standalone = connectors.get_credential("u1", "github", ["repo"])
    assert isinstance(standalone, connectors.NeedsConsent)

    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service("github", "GitHub")
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {"access_token": "token-u1", "scopes": ["repo"]},
        updated_by="u1",
    )

    async def _noop_reconcile() -> None:
        return None

    with (
        patch("fleetent.runtime.approval_resume.reconcile_expired_approvals", _noop_reconcile),
        TestClient(app),
    ):
        injected = connectors.get_credential("u1", "github", ["repo"])

    assert isinstance(injected, connectors.Credential)
    assert injected.client["access_token"] == "token-u1"


def test_vault_provider_refreshes_expired_token_and_rewrites_payload(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"token": "https://github.example/oauth/token", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-u1",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        refresh_route = router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "fresh-token",
                    "refresh_token": "refresh-u2",
                    "expires_in": 3600,
                    "scope": "repo",
                    "token_type": "Bearer",
                },
            )
        )
        result = provider.get_credential("u1", "github", ["repo"])

    assert refresh_route.called
    assert isinstance(result, connectors.Credential)
    assert result.client["access_token"] == "fresh-token"
    assert result.client["refresh_token"] == "refresh-u2"
    stored = external_credential_store.get_credential("u1", "github")
    assert stored is not None
    assert stored["status"] == "authorized"
    assert stored["payload"]["access_token"] == "fresh-token"
    assert stored["payload"]["refresh_token"] == "refresh-u2"
    assert "expires_at" in stored["payload"]


def test_vault_provider_does_not_refresh_when_token_still_valid(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"token": "https://github.example/oauth/token", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "still-valid-token",
            "refresh_token": "refresh-u1",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=False) as router:
        token_route = router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "should-not-run"})
        )
        result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.Credential)
    assert result.client["access_token"] == "still-valid-token"
    assert token_route.called is False


def test_vault_provider_returns_needs_consent_when_refresh_token_invalid(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"token": "https://github.example/oauth/token", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-u1",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://github.example/oauth/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.NeedsConsent)
    stored = external_credential_store.get_credential("u1", "github")
    assert stored is not None
    assert stored["status"] == "needs_reauth"


def test_vault_provider_returns_retryable_error_when_refresh_request_fails(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"token": "https://github.example/oauth/token", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-u1",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://github.example/oauth/token").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.CredentialError)
    assert result.connector == "github"
    assert result.retryable is True
    stored = external_credential_store.get_credential("u1", "github")
    assert stored is not None
    assert stored["status"] == "error"


def test_vault_provider_refresh_failure_does_not_log_tokens(provider_db, caplog: LogCaptureFixture):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"token": "https://github.example/oauth/token", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-u1",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://github.example/oauth/token").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        result = provider.get_credential("u1", "github", ["repo"])

    assert isinstance(result, connectors.CredentialError)
    rendered = f"{result!r} {caplog.text}"
    assert "expired-token" not in rendered
    assert "refresh-u1" not in rendered


def test_vault_provider_revoke_deletes_local_credential_and_calls_remote(provider_db):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"revoke": "https://github.example/oauth/revoke", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {"access_token": "token-u1", "refresh_token": "refresh-u1"},
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        revoke_route = router.post("https://github.example/oauth/revoke").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = provider.revoke_credential("u1", "github")

    assert revoke_route.called
    assert result == {"revoked": True}
    assert external_credential_store.get_credential("u1", "github") is None


def test_vault_provider_revoke_remote_failure_still_deletes_local_credential(
    provider_db, caplog: LogCaptureFixture
):
    provider = _provider_module()
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service(
        "github",
        "GitHub",
        oauth_config={"revoke": "https://github.example/oauth/revoke", "client_id": "cid-123"},
    )
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {"access_token": "token-u1", "refresh_token": "refresh-u1"},
        updated_by="u1",
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://github.example/oauth/revoke").mock(
            side_effect=httpx.ConnectError("network down")
        )
        result = provider.revoke_credential("u1", "github")

    assert result == {"revoked": True}
    assert external_credential_store.get_credential("u1", "github") is None
    assert "token-u1" not in caplog.text
    assert "refresh-u1" not in caplog.text
