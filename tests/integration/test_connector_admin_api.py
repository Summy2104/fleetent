from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
from fleetent.config import mcp_yaml_field_paths
from fleetent.platform.connector_management import connector_admin_api, mcp_server_store
from tests.integration._migration_template import apply_migrations


@dataclass
class _User:
    id: str = "admin"


def test_mcp_admin_api_accepts_structured_auth_and_rejects_legacy_secret_fields(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(connector_admin_api, "_current_user", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api, "_require_admin", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api.audit_log, "write_audit", lambda *args, **kwargs: None)

    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    monkeypatch.setattr(connector_admin_api, "mcp_sync_server", _noop_sync)

    app = FastAPI()
    app.include_router(connector_admin_api.router)
    client = TestClient(app, raise_server_exceptions=True)
    headers = {"Authorization": "Session ignored"}
    agent = agent_store.create_agent("docs-agent", "p", [])

    create = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "docs",
            "agent_id": agent.id,
            "transport": "http",
            "url": "https://docs.internal/mcp",
            "auth_type": "api_key",
            "auth_config": {"key_env": "FLEETENT_DOCS_MCP_KEY"},
        },
    )
    assert create.status_code == 200
    row = mcp_server_store.get_mcp_server(agent.id, "docs")
    assert row is not None
    assert row["auth_type"] == "api_key"
    assert row["auth_config"] == {"key_env": "FLEETENT_DOCS_MCP_KEY"}

    edit = client.put(
        "/admin/mcp/servers/docs",
        params={"agent_id": agent.id},
        headers=headers,
        json={
            "auth_type": "oauth_client_credentials",
            "auth_config": {
                "token_url": "https://auth.internal/token",
                "client_id": "docs-client",
                "client_secret_env": "FLEETENT_DOCS_MCP_SECRET",
                "scope": "tools:read",
            },
        },
    )
    assert edit.status_code == 200
    updated = mcp_server_store.get_mcp_server(agent.id, "docs")
    assert updated is not None
    assert updated["auth_type"] == "oauth_client_credentials"
    assert updated["auth_config"] == {
        "token_url": "https://auth.internal/token",
        "client_id": "docs-client",
        "client_secret_env": "FLEETENT_DOCS_MCP_SECRET",
        "scope": "tools:read",
    }

    legacy = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "legacy",
            "transport": "http",
            "url": "https://legacy.internal/mcp",
            "auth_type": "api_key",
            "api_key_env": "FLEETENT_LEGACY_MCP_KEY",
        },
    )
    assert legacy.status_code == 422

    plaintext = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "oauth-plain",
            "transport": "http",
            "url": "https://oauth.internal/mcp",
            "auth_type": "oauth_client_credentials",
            "auth_config": {
                "token_url": "https://auth.internal/token",
                "client_id": "docs-client",
                "client_secret": "super-secret",
            },
        },
    )
    assert plaintext.status_code == 422


def test_mcp_admin_api_list_does_not_mask_auth_config_and_edit_round_trips_it(
    tmp_path, monkeypatch
) -> None:
    """auth_config only ever holds env-var references, never secret values (mcp_auth_models),
    so the list endpoint must not mask it — masking it broke edits: the browser round-trips
    whatever the list endpoint returned, so a masked placeholder was previously saved back
    over the real token_url / client_secret_env, corrupting the server's config."""
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(connector_admin_api, "_current_user", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api, "_require_admin", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api.audit_log, "write_audit", lambda *args, **kwargs: None)

    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    monkeypatch.setattr(connector_admin_api, "mcp_sync_server", _noop_sync)

    app = FastAPI()
    app.include_router(connector_admin_api.router)
    client = TestClient(app, raise_server_exceptions=True)
    headers = {"Authorization": "Session ignored"}

    client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "docs-oauth",
            "transport": "http",
            "url": "https://docs.internal/mcp",
            "auth_type": "oauth_client_credentials",
            "auth_config": {
                "token_url": "https://auth.internal/token",
                "client_id": "docs-client",
                "client_secret_env": "FLEETENT_DOCS_MCP_SECRET",
                "scope": "tools:read",
            },
        },
    )

    listed = client.get("/admin/mcp/servers", headers=headers).json()
    server = next(s for s in listed if s["id"] == "docs-oauth")
    assert server["auth_config"] == {
        "token_url": "https://auth.internal/token",
        "client_id": "docs-client",
        "client_secret_env": "FLEETENT_DOCS_MCP_SECRET",
        "scope": "tools:read",
    }

    # The browser re-submits the full auth_config on every edit, including fields the
    # admin never touched -- those must be whatever list returned, not a placeholder.
    edit = client.put(
        "/admin/mcp/servers/docs-oauth",
        headers=headers,
        json={
            "auth_type": "oauth_client_credentials",
            "auth_config": {**server["auth_config"], "scope": "tools:read tools:write"},
        },
    )
    assert edit.status_code == 200

    updated = mcp_server_store.get_mcp_server(None, "docs-oauth")
    assert updated is not None
    assert updated["auth_config"] == {
        "token_url": "https://auth.internal/token",
        "client_id": "docs-client",
        "client_secret_env": "FLEETENT_DOCS_MCP_SECRET",
        "scope": "tools:read tools:write",
    }


def test_field_schema_returns_yaml_field_paths_for_any_logged_in_user(monkeypatch) -> None:
    monkeypatch.setattr(connector_admin_api, "_current_user", lambda _authorization: _User())

    app = FastAPI()
    app.include_router(connector_admin_api.router)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.get("/admin/mcp/field-schema", headers={"Authorization": "Session ignored"})

    assert response.status_code == 200
    assert response.json() == mcp_yaml_field_paths()


def test_field_schema_rejects_unauthenticated_request() -> None:
    app = FastAPI()
    app.include_router(connector_admin_api.router)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.get("/admin/mcp/field-schema")

    assert response.status_code == 401


def _xfleetent_client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(connector_admin_api, "_current_user", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api, "_require_admin", lambda _authorization: _User())
    monkeypatch.setattr(connector_admin_api.audit_log, "write_audit", lambda *a, **k: None)

    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    monkeypatch.setattr(connector_admin_api, "mcp_sync_server", _noop_sync)
    app = FastAPI()
    app.include_router(connector_admin_api.router)
    return TestClient(app, raise_server_exceptions=True)


def test_mcp_admin_api_round_trips_xfleetent_fields(tmp_path, monkeypatch) -> None:
    client = _xfleetent_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Session ignored"}

    create = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "billing",
            "transport": "stdio",
            "command": "npx",
            "degrade_mode": "strict",
            "file_root": "/exchange/billing",
            "file_isolation": "off",
            "approval_rules": [{"tool": "manage_email", "when": {"operation": ["send", "reply"]}}],
        },
    )
    assert create.status_code == 200
    row = mcp_server_store.get_mcp_server(None, "billing")
    assert row is not None
    assert row["degrade_mode"] == "strict"
    assert row["file_root"] == "/exchange/billing"
    assert row["file_isolation"] == "off"
    assert row["approval_rules"] == [
        {"tool": "manage_email", "when": {"operation": ["send", "reply"]}}
    ]

    listed = client.get("/admin/mcp/servers", headers=headers).json()
    server = next(s for s in listed if s["id"] == "billing")
    assert server["degrade_mode"] == "strict"
    assert server["file_root"] == "/exchange/billing"
    assert server["file_isolation"] == "off"
    assert server["approval_rules"] == [
        {"tool": "manage_email", "when": {"operation": ["send", "reply"]}}
    ]

    # A whole-tool rule (no when) round-trips as when=None.
    edit = client.put(
        "/admin/mcp/servers/billing",
        headers=headers,
        json={"degrade_mode": "silent", "approval_rules": [{"tool": "delete_file"}]},
    )
    assert edit.status_code == 200
    updated = mcp_server_store.get_mcp_server(None, "billing")
    assert updated is not None
    assert updated["degrade_mode"] == "silent"
    assert updated["approval_rules"] == [{"tool": "delete_file", "when": None}]
    assert updated["file_isolation"] == "off"


def test_mcp_admin_api_rejects_invalid_xfleetent_values(tmp_path, monkeypatch) -> None:
    client = _xfleetent_client(tmp_path, monkeypatch)
    headers = {"Authorization": "Session ignored"}

    bad_degrade = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={"id": "x1", "transport": "stdio", "command": "e", "degrade_mode": "loud"},
    )
    assert bad_degrade.status_code == 422

    bad_rule = client.post(
        "/admin/mcp/servers",
        headers=headers,
        json={
            "id": "x2",
            "transport": "stdio",
            "command": "e",
            "approval_rules": [{"when": {"operation": ["send"]}}],
        },
    )
    assert bad_rule.status_code == 422
