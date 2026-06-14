"""Integration tests for the vault credential provider and platform seam wiring."""

from __future__ import annotations

import base64
import importlib
import importlib.util
from unittest.mock import patch

import pytest
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
    from fleetent.platform.connector_management import external_credential_store, external_service_store

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

    from fleetent.platform.connector_management import external_credential_store, external_service_store

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
