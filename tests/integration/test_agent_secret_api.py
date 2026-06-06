"""Integration tests for write-only agent credential APIs."""

import base64
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.model_provider_management import provider_admin_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
    )
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
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
        auth_type="bearer",
        api_key_env="FLEETENT_AGENT_SUPPORT_DOCS",
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
        auth_type="bearer",
        api_key_env="FLEETENT_AGENT_SUPPORT_JIRA",
    )
    agent_store.bind_mcp_server(agent_id, "jira")
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/support/required-env", headers=_hdr(token)).json()

    env_names = {item["env_name"] for item in body["required_env"]}
    assert "FLEETENT_AGENT_SUPPORT_JIRA" in env_names
    assert "DATABASE_URL" not in env_names
    assert "FLEETENT_SECRET_KEY" not in env_names


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
    slot = {
        item["env_name"]: item for item in listed.json()["secrets"]
    }["FLEETENT_AGENT_SUPPORT_MODEL"]
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
