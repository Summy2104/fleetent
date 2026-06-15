"""Integration tests for P5: wiring connector admin API to the real Vault.

Tasks:
  1.1 connectors_list_grants — real matrix from external_credentials status
  2.1 connectors_revoke — calls vault_provider.revoke_credential, audit, viewer 403
  3.1 connectors_offboarding_result — revokes all user credentials
  4.1 connector_lifecycle_stats — counts derived from status column
  5.1 security: no plaintext token in any response
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.connector_management.connector_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.connector_management import external_credential_store
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
    app = FastAPI()
    app.include_router(api.router)

    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    async def _fake_probe(server_id: str) -> dict[str, Any]:
        return {"connected": True, "tool_count": 0, "tools": []}

    app.state.mcp_sync_server = _noop_sync
    app.state.mcp_probe = _fake_probe
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict[str, str]:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


def _seed_cred(
    user_id: str,
    service_id: str,
    status: str = "authorized",
    payload: dict[str, Any] | None = None,
) -> None:
    external_credential_store.put_oauth_credential(
        user_id,
        service_id,
        payload or {"access_token": "tok-test"},
        status=status,
    )


# ---------------------------------------------------------------------------
# 1.1 connectors_list_grants — authorization matrix from real Vault
# ---------------------------------------------------------------------------


def test_list_grants_empty_when_no_credentials(vault_db):
    result = api.connectors_list_grants()
    assert result == []


def test_list_grants_returns_credentials_with_status_mapping(vault_db):
    _seed_cred("u1", "github", status="authorized")
    _seed_cred("u2", "github", status="needs_reauth")
    _seed_cred("u3", "github", status="error")

    result = api.connectors_list_grants()

    assert len(result) == 3
    by_user = {r["user_id"]: r["status"] for r in result}
    assert by_user["u1"] == "authorized"
    assert by_user["u2"] == "needs_reauth"
    assert by_user["u3"] == "credential_error"


def test_list_grants_no_payload_plaintext(vault_db):
    _seed_cred("u1", "github", payload={"access_token": "super-secret", "refresh_token": "also-secret"})
    result = api.connectors_list_grants()
    assert result  # must have a row
    row = result[0]
    # No plaintext credential values in matrix row
    for v in row.values():
        if isinstance(v, str):
            assert "super-secret" not in v
            assert "also-secret" not in v


def test_list_grants_multi_service_multi_user_consistent(vault_db):
    _seed_cred("u1", "github", status="authorized")
    _seed_cred("u1", "slack", status="needs_reauth")
    _seed_cred("u2", "github", status="error")

    result = api.connectors_list_grants()
    assert len(result) == 3

    # By-user view: filter u1 → 2 services
    u1_rows = [r for r in result if r["user_id"] == "u1"]
    assert {r["connector_id"] for r in u1_rows} == {"github", "slack"}

    # By-service view: filter github → 2 users
    gh_rows = [r for r in result if r["connector_id"] == "github"]
    assert {r["user_id"] for r in gh_rows} == {"u1", "u2"}


def test_list_grants_agent_id_ignored(vault_db):
    """agent_id param is accepted but result is global-only (spec: no owning-agent dimension)."""
    _seed_cred("u1", "github")

    result_no_agent = api.connectors_list_grants(agent_id=None)
    result_with_agent = api.connectors_list_grants(agent_id=99)

    assert result_no_agent == result_with_agent


def test_list_grants_via_http_masks_tokens(client, vault_db):
    # Token masking happens at the endpoint layer via _mask()
    _seed_cred("u1", "github", payload={"access_token": "plaintext-tok", "refresh_token": "ref"})
    token, _ = _session_for("admin")
    r = client.get("/admin/connectors/grants", headers=_hdr(token))
    assert r.status_code == 200
    for grant in r.json()["grants"]:
        for k, v in grant.items():
            # No sensitive key should carry a real value through
            if any(s in k for s in ("token", "secret", "password", "api_key")):
                assert v == "****", f"key {k!r} leaked value {v!r}"


# ---------------------------------------------------------------------------
# 2.1 connectors_revoke — calls vault, writes audit, viewer 403
# ---------------------------------------------------------------------------


def test_revoke_deletes_vault_credential(vault_db):
    _seed_cred("u1", "github")
    assert external_credential_store.get_credential("u1", "github") is not None

    result = api.connectors_revoke("u1", "github")

    assert result["revoked"] is True
    assert external_credential_store.get_credential("u1", "github") is None


def test_revoke_already_absent_returns_revoked_true(vault_db):
    result = api.connectors_revoke("u1", "nobody")
    assert result["revoked"] is True


def test_revoke_requires_confirm_header_via_http(client, vault_db):
    _seed_cred("u1", "github")
    token, _ = _session_for("admin")
    # Without X-Confirm: true → 428
    r = client.post("/admin/connectors/grants/u1/github/revoke", headers=_hdr(token))
    assert r.status_code == 428


def test_revoke_via_http_writes_audit_and_deletes_credential(client, vault_db):
    _seed_cred("u1", "github")
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/connectors/grants/u1/github/revoke", headers=_hdr(token, confirm=True)
    )
    assert r.status_code == 200
    assert r.json()["revoked"] is True
    assert external_credential_store.get_credential("u1", "github") is None
    assert any(
        a["action"] == "connector.revoke" and a["target_id"] == "github"
        for a in audit.search_audit()
    )


def test_revoke_viewer_forbidden(client, vault_db):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/connectors/grants/u1/github/revoke", headers=_hdr(token, confirm=True)
    )
    assert r.status_code == 403


def test_revoke_response_has_no_token_plaintext(client, vault_db):
    _seed_cred("u1", "github", payload={"access_token": "secret-val"})
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/connectors/grants/u1/github/revoke", headers=_hdr(token, confirm=True)
    )
    body = r.json()
    import json

    body_str = json.dumps(body)
    assert "secret-val" not in body_str


# ---------------------------------------------------------------------------
# 3.1 connectors_offboarding_result — revoke all user credentials
# ---------------------------------------------------------------------------


def test_offboarding_revokes_all_user_credentials(vault_db):
    _seed_cred("u1", "github", payload={"api_key": "k1"})  # apikey-style; no HTTP revoke
    _seed_cred("u1", "slack", payload={"api_key": "k2"})

    result = api.connectors_offboarding_result("u1")

    assert set(result["revoked"]) == {"github", "slack"}
    assert result["failed"] == []
    assert external_credential_store.get_credential("u1", "github") is None
    assert external_credential_store.get_credential("u1", "slack") is None


def test_offboarding_no_credentials_returns_empty_lists(vault_db):
    result = api.connectors_offboarding_result("nobody")
    assert result == {"user_id": "nobody", "revoked": [], "failed": []}


def test_offboarding_other_users_credentials_untouched(vault_db):
    _seed_cred("u1", "github")
    _seed_cred("u2", "github")

    api.connectors_offboarding_result("u1")

    # u2's credential should be untouched
    assert external_credential_store.get_credential("u2", "github") is not None


def test_offboarding_via_http_returns_result(client, vault_db):
    _seed_cred("u1", "github")
    token, _ = _session_for("admin")
    r = client.get("/admin/connectors/offboarding/u1", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert "revoked" in body
    assert "failed" in body


def test_offboarding_partial_failure_reported(vault_db):
    """If vault_provider.revoke_credential raises, service goes to failed list."""
    _seed_cred("u1", "github")
    _seed_cred("u1", "slack")

    with patch(
        "fleetent.platform.connector_management.vault_provider.revoke_credential",
        side_effect=[{"revoked": True}, Exception("network error")],
    ):
        result = api.connectors_offboarding_result("u1")

    assert len(result["revoked"]) == 1
    assert len(result["failed"]) == 1


# ---------------------------------------------------------------------------
# 4.1 connector_lifecycle_stats — counts from status column
# ---------------------------------------------------------------------------


def test_lifecycle_stats_counts_by_status(vault_db):
    _seed_cred("u1", "github", status="authorized")
    _seed_cred("u2", "github", status="authorized")
    _seed_cred("u3", "github", status="needs_reauth")
    _seed_cred("u4", "github", status="error")

    stats = api.connector_lifecycle_stats("github")

    assert stats["connector_id"] == "github"
    assert stats["refresh_ok"] == 2  # authorized
    assert stats["refresh_failed"] == 1  # error
    assert stats["reauths"] == 1  # needs_reauth


def test_lifecycle_stats_unknown_connector_returns_zeros(vault_db):
    stats = api.connector_lifecycle_stats("unknown-svc")
    assert stats == {"connector_id": "unknown-svc", "refresh_ok": 0, "refresh_failed": 0, "reauths": 0}


def test_lifecycle_stats_via_http(client, vault_db):
    _seed_cred("u1", "github", status="authorized")
    token, _ = _session_for("viewer")
    r = client.get("/admin/connectors/github/lifecycle", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_ok"] == 1
    assert body["refresh_failed"] == 0


def test_lifecycle_stats_no_token_plaintext(vault_db):
    """Stats contain only counts — verify no sensitive value leaks."""
    _seed_cred("u1", "github", payload={"access_token": "should-not-appear"})
    stats = api.connector_lifecycle_stats("github")
    import json

    stats_str = json.dumps(stats)
    assert "should-not-appear" not in stats_str


# ---------------------------------------------------------------------------
# 5.1 security: masking layer covers all views
# ---------------------------------------------------------------------------


def test_matrix_endpoint_masks_sensitive_keys(client, vault_db):
    """If any grant row somehow carries a sensitive key, _mask() must redact it."""
    # Simulate a row with sensitive keys (testing the _mask layer at endpoint)
    import fleetent.platform.connector_management.connector_admin_api as _api

    def _leaky_grants(agent_id=None):
        return [
            {
                "user_id": "u1",
                "connector_id": "gh",
                "status": "authorized",
                "access_token": "leaked-tok",
                "client_secret": "leaked-secret",
            }
        ]

    original = _api.connectors_list_grants
    try:
        _api.connectors_list_grants = _leaky_grants
        token, _ = _session_for("admin")
        r = client.get("/admin/connectors/grants", headers=_hdr(token))
        g = r.json()["grants"][0]
        assert g.get("access_token") == "****"
        assert g.get("client_secret") == "****"
    finally:
        _api.connectors_list_grants = original
