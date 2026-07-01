from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
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
