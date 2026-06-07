"""Write-only credential API + required-env derivation (admin console face)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.model_provider_management import provider_admin_store

_SECRET = "xoxb-do-not-echo-me"


def _migrate(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    _migrate(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _admin_hdr() -> dict:
    u = user_store.create_user("admin-user")
    user_store.set_role(u.id, "admin")
    return {"Authorization": f"Session {auth.create_session(u.id)}"}


def _seed_agent_with_model_and_mcp() -> agent_store.Agent:
    provider_admin_store.add_provider(
        "anthropic-primary",
        base_url="https://api.anthropic.com/v1/",
        model="claude-opus-4-8",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_MODEL_PRIMARY_API_KEY",
    )
    agent_mcp_server_store.add_mcp_server(
        None, "docs", transport="http", url="https://x/mcp", api_key_env="ACME_DOCS_MCP_TOKEN"
    )
    agent = agent_store.create_agent(
        "support",
        "Help.",
        ["shell"],
        model_overrides={"default": {"provider": "anthropic-primary", "model": "claude-opus-4-8"}},
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    return agent


def test_required_env_lists_slots_with_source_mode_status(client):
    _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    resp = client.get("/admin/agents/support/required-env", headers=hdr)
    assert resp.status_code == 200
    by_env = {s["env_name"]: s for s in resp.json()["slots"]}
    assert by_env["FLEETENT_MODEL_PRIMARY_API_KEY"]["source"].startswith("Models")
    assert by_env["ACME_DOCS_MCP_TOKEN"]["source"].startswith("MCP")
    # default operator + unset before any value
    assert by_env["ACME_DOCS_MCP_TOKEN"]["mode"] == "operator"
    assert by_env["ACME_DOCS_MCP_TOKEN"]["status"] == "unset"


def test_put_secret_does_not_echo_value(client):
    _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    resp = client.put(
        "/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN",
        headers=hdr,
        json={"value": _SECRET},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"env_name": "ACME_DOCS_MCP_TOKEN", "status": "set"}
    assert _SECRET not in resp.text


def test_secrets_list_never_contains_plaintext(client):
    _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    client.put(
        "/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN", headers=hdr, json={"value": _SECRET}
    )
    resp = client.get("/admin/agents/support/secrets", headers=hdr)
    assert resp.status_code == 200
    assert _SECRET not in resp.text
    by_env = {s["env_name"]: s for s in resp.json()["slots"]}
    assert by_env["ACME_DOCS_MCP_TOKEN"]["mode"] == "inject"
    assert by_env["ACME_DOCS_MCP_TOKEN"]["status"] == "set"


def test_empty_value_rejected(client):
    _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    resp = client.put(
        "/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN", headers=hdr, json={"value": ""}
    )
    assert resp.status_code == 400


def test_delete_clears_to_operator(client):
    _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    client.put(
        "/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN", headers=hdr, json={"value": _SECRET}
    )
    assert (
        client.delete("/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN", headers=hdr).status_code
        == 200
    )
    resp = client.get("/admin/agents/support/secrets", headers=hdr)
    by_env = {s["env_name"]: s for s in resp.json()["slots"]}
    assert by_env["ACME_DOCS_MCP_TOKEN"]["status"] == "unset"


def test_required_env_reflects_new_mcp_binding(client):
    agent = _seed_agent_with_model_and_mcp()
    hdr = _admin_hdr()
    agent_mcp_server_store.add_mcp_server(
        None, "billing", transport="http", url="https://y/mcp", api_key_env="BILLING_MCP_TOKEN"
    )
    agent_store.bind_mcp_server(agent.id, "billing")
    resp = client.get("/admin/agents/support/required-env", headers=hdr)
    envs = {s["env_name"] for s in resp.json()["slots"]}
    assert "BILLING_MCP_TOKEN" in envs


def test_secret_write_requires_admin(client):
    _seed_agent_with_model_and_mcp()
    viewer = user_store.create_user("viewer-user")
    user_store.set_role(viewer.id, "viewer")
    hdr = {"Authorization": f"Session {auth.create_session(viewer.id)}"}
    resp = client.put(
        "/admin/agents/support/secrets/ACME_DOCS_MCP_TOKEN", headers=hdr, json={"value": _SECRET}
    )
    assert resp.status_code == 403
