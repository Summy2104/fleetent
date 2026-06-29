"""Integration tests for write-only agent credential APIs."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.platform.agent_management_console.agent_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.model_provider_management import provider_admin_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
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


def _create_agent_with_required_env() -> int:
    provider_admin_store.add_provider(
        "claude-fast",
        "https://api.anthropic.com/v1/",
        "claude-haiku-4-5-20251001",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    agent = agent_store.create_agent(
        "support",
        "p",
        ["docs__*"],
        mcp_server_ids=["docs"],
        model_overrides={"default": [{"provider_id": "claude-fast"}]},
    )
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.internal/mcp",
        auth_type="api_key",
        auth_config={"key_env": "FLEETENT_AGENT_SUPPORT_DOCS"},
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    return agent.id


def test_required_env_derives_current_model_and_mcp_refs(client):
    _create_agent_with_required_env()
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/support/required-env", headers=_hdr(token)).json()

    refs = {item["env_name"]: item for item in body["required_env"]}
    assert refs["FLEETENT_AGENT_SUPPORT_MODEL"]["source"] == "Models"
    assert refs["FLEETENT_AGENT_SUPPORT_MODEL"]["mode"] == "operator"
    assert refs["FLEETENT_AGENT_SUPPORT_MODEL"]["status"] == "unset"
    assert refs["FLEETENT_AGENT_SUPPORT_DOCS"]["source"] == "MCP"


def test_required_env_reflects_new_mcp_without_false_positives(client):
    agent_id = _create_agent_with_required_env()
    agent_mcp_server_store.add_mcp_server(
        None,
        "jira",
        transport="http",
        url="https://jira.internal/mcp",
        auth_type="api_key",
        auth_config={"key_env": "FLEETENT_AGENT_SUPPORT_JIRA"},
    )
    agent_store.bind_mcp_server(agent_id, "jira")
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/support/required-env", headers=_hdr(token)).json()

    env_names = {item["env_name"] for item in body["required_env"]}
    assert "FLEETENT_AGENT_SUPPORT_JIRA" in env_names
    assert "DATABASE_URL" not in env_names
    assert "FLEETENT_SECRET_KEY" not in env_names


def test_required_env_includes_mcp_env_and_header_refs(client):
    """MCP env/headers 里的 env:XXX 引用要进 required-env；明文值不算（mcp-secret-via-ui）。"""
    agent = agent_store.create_agent("support", "p", [], mcp_server_ids=["jira", "armada"])
    agent_mcp_server_store.add_mcp_server(
        None,
        "jira",
        transport="stdio",
        command="npx",
        args=["-y", "@aashari/mcp-server-atlassian-jira"],
        env={"ATLASSIAN_API_TOKEN": "env:ATLASSIAN_API_TOKEN"},
    )
    agent_mcp_server_store.add_mcp_server(
        None,
        "armada",
        transport="http",
        url="https://armada.internal/mcp",
        headers={"Authorization": "env:ARMADA_AUTH", "X-Static": "plain-value"},
    )
    agent_store.bind_mcp_server(agent.id, "jira")
    agent_store.bind_mcp_server(agent.id, "armada")
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/support/required-env", headers=_hdr(token)).json()

    refs = {item["env_name"]: item for item in body["required_env"]}
    assert refs["ATLASSIAN_API_TOKEN"]["source"] == "MCP"
    assert refs["ARMADA_AUTH"]["source"] == "MCP"
    assert "plain-value" not in refs  # 明文 header 值不被当成 env 名


def test_required_env_includes_mcp_oauth_auth_refs(client):
    """MCP per-server OAuth(x-fleetent.auth) 的 client_secret_env 与 client_id 的 env:
    引用要进 required-env——否则这些只活在 auth 块里的密钥无法在 UI 密钥页设置。"""
    agent_store.create_agent(
        "support",
        "p",
        [],
        config_overrides={
            "mcpServers": {
                "gdrive": {
                    "url": "https://drive.example/mcp",
                    "x-fleetent": {
                        "auth": {
                            "type": "oauth2",
                            "grant": "authorization_code",
                            "token_url": "https://oauth.example/token",
                            "authorization_endpoint": "https://oauth.example/auth",
                            "redirect_path": "/oauth/callback",
                            "client_id": "env:GDRIVE_CLIENT_ID",
                            "client_secret_env": "GDRIVE_CLIENT_SECRET",
                            "scope": "drive.readonly",
                        }
                    },
                }
            }
        },
    )
    token, _ = _session_for("admin")

    body = client.get("/admin/agents/support/required-env", headers=_hdr(token)).json()

    refs = {item["env_name"]: item for item in body["required_env"]}
    assert refs["GDRIVE_CLIENT_SECRET"]["source"] == "MCP"  # client_secret_env 是 env 名
    assert refs["GDRIVE_CLIENT_ID"]["source"] == "MCP"  # client_id 的 env: 引用


def test_secret_api_is_write_only_and_delete_clears_value(client):
    _create_agent_with_required_env()
    token, _ = _session_for("admin")

    put = client.put(
        "/admin/agents/support/secrets/FLEETENT_AGENT_SUPPORT_MODEL",
        headers=_hdr(token),
        json={"value": "sk-live-secret"},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"env_name": "FLEETENT_AGENT_SUPPORT_MODEL", "status": "set"}
    assert "sk-live-secret" not in put.text

    listed = client.get("/admin/agents/support/secrets", headers=_hdr(token))
    assert "sk-live-secret" not in listed.text
    slot = {item["env_name"]: item for item in listed.json()["secrets"]}[
        "FLEETENT_AGENT_SUPPORT_MODEL"
    ]
    assert slot == {
        "env_name": "FLEETENT_AGENT_SUPPORT_MODEL",
        "mode": "inject",
        "status": "set",
    }

    deleted = client.delete(
        "/admin/agents/support/secrets/FLEETENT_AGENT_SUPPORT_MODEL",
        headers=_hdr(token),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"env_name": "FLEETENT_AGENT_SUPPORT_MODEL", "status": "unset"}


def test_secret_api_rejects_empty_values(client):
    _create_agent_with_required_env()
    token, _ = _session_for("admin")

    response = client.put(
        "/admin/agents/support/secrets/FLEETENT_AGENT_SUPPORT_MODEL",
        headers=_hdr(token),
        json={"value": ""},
    )

    assert response.status_code == 400
    assert "delete" in response.json()["detail"]
