"""Unit tests for ServiceProvider adapter interface and factory (Task 1.1).

Pure-function tests only — no DB, no HTTP, no FastAPI.
"""

from __future__ import annotations

import pytest

import fleetent.platform.connector_management.service_providers as _sp_module
from fleetent.platform.connector_management.service_providers import (
    _GenericOAuth2Provider,
    _GitHubProvider,
    _GoogleDriveProvider,
    client_secret_for,
    get_provider,
    register_provider,
)


@pytest.fixture(autouse=True)
def restore_registry():
    before = dict(_sp_module._REGISTRY)
    yield
    _sp_module._REGISTRY.clear()
    _sp_module._REGISTRY.update(before)


# ---------------------------------------------------------------------------
# build_authorize_params
# ---------------------------------------------------------------------------


def test_generic_build_authorize_params_standard_fields():
    p = _GenericOAuth2Provider()
    params = p.build_authorize_params("cid-123", "https://app/callback", "state-abc", ["repo"])
    assert params["response_type"] == "code"
    assert params["client_id"] == "cid-123"
    assert params["redirect_uri"] == "https://app/callback"
    assert params["state"] == "state-abc"
    assert params["scope"] == "repo"


def test_generic_multiple_scopes_space_joined():
    p = _GenericOAuth2Provider()
    params = p.build_authorize_params("c", "u", "s", ["read", "write"])
    assert params["scope"] == "read write"


def test_generic_empty_scopes_omits_scope_key():
    p = _GenericOAuth2Provider()
    params = p.build_authorize_params("c", "u", "s", [])
    assert "scope" not in params


def test_google_drive_adds_offline_and_consent():
    p = _GoogleDriveProvider()
    params = p.build_authorize_params("cid", "https://cb", "st", ["drive.readonly"])
    assert params["access_type"] == "offline"
    assert params["prompt"] == "consent"
    # also has standard fields
    assert params["response_type"] == "code"
    assert "drive.readonly" in params.get("scope", "")


def test_github_no_offline_params():
    p = _GitHubProvider()
    params = p.build_authorize_params("cid", "https://cb", "st", ["repo"])
    assert "access_type" not in params
    assert "prompt" not in params
    assert params["scope"] == "repo"


# ---------------------------------------------------------------------------
# build_client
# ---------------------------------------------------------------------------


def test_generic_build_client_includes_all_payload_fields():
    p = _GenericOAuth2Provider()
    payload = {
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_at": "2030-01-01T00:00:00+00:00",
    }
    client = p.build_client(payload, ["repo"])
    assert client["access_token"] == "tok"
    assert client["refresh_token"] == "ref"  # preserved for backward compat
    assert client["scopes"] == ["repo"]


def test_generic_build_client_does_not_overwrite_existing_scopes():
    p = _GenericOAuth2Provider()
    payload = {"access_token": "t", "scopes": ["already"]}
    client = p.build_client(payload, ["new"])
    assert client["scopes"] == ["already"]  # setdefault: original wins


def test_generic_build_client_no_scopes_omits_scopes_key():
    p = _GenericOAuth2Provider()
    client = p.build_client({"access_token": "t"}, [])
    assert "scopes" not in client


def test_build_client_does_not_mutate_original_payload():
    p = _GenericOAuth2Provider()
    payload = {"access_token": "t"}
    p.build_client(payload, ["repo"])
    assert "scopes" not in payload


# ---------------------------------------------------------------------------
# normalize_scopes
# ---------------------------------------------------------------------------


def test_generic_normalize_scopes_passthrough():
    p = _GenericOAuth2Provider()
    assert p.normalize_scopes(["a", "b"]) == ["a", "b"]


def test_github_normalize_scopes_passthrough():
    p = _GitHubProvider()
    assert p.normalize_scopes(["repo", "read:org"]) == ["repo", "read:org"]


# ---------------------------------------------------------------------------
# client_secret_for
# ---------------------------------------------------------------------------


def test_client_secret_for_reads_env(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret-val")
    assert client_secret_for("github") == "gh-secret-val"


def test_client_secret_for_hyphenated_service(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "gd-secret-val")
    assert client_secret_for("google-drive") == "gd-secret-val"


def test_client_secret_for_missing_returns_empty_string():
    # Ensure no env var is set for this fictitious service
    assert client_secret_for("totally-unknown-service-xyz") == ""


# ---------------------------------------------------------------------------
# factory routing
# ---------------------------------------------------------------------------


def test_factory_returns_google_drive_for_google_drive():
    p = get_provider("google-drive")
    params = p.build_authorize_params("c", "u", "s", [])
    assert params.get("access_type") == "offline"


def test_factory_returns_github_for_github():
    p = get_provider("github")
    params = p.build_authorize_params("c", "u", "s", [])
    assert "access_type" not in params


def test_factory_falls_back_to_generic_for_unknown():
    p = get_provider("acme-unknown-xyz")
    # Must be callable and return standard params
    params = p.build_authorize_params("c", "u", "s", ["r"])
    assert params["response_type"] == "code"
    assert "access_type" not in params


def test_register_provider_custom_adapter():
    class _AcmeProvider(_GenericOAuth2Provider):
        def build_authorize_params(self, client_id, redirect_uri, state, scopes):
            params = super().build_authorize_params(client_id, redirect_uri, state, scopes)
            params["acme_custom"] = "1"
            return params

    register_provider("acme-crm", _AcmeProvider())
    p = get_provider("acme-crm")
    params = p.build_authorize_params("c", "u", "s", [])
    assert params.get("acme_custom") == "1"


def test_register_provider_overrides_existing():
    class _CustomGH(_GenericOAuth2Provider):
        pass

    custom = _CustomGH()
    register_provider("github", custom)
    assert get_provider("github") is custom
