"""Tests for agent_admin_api (/admin/agents version + binding REST).

Covers multi-agent-management tasks 11.1/11.3: version listing + activation and the
four binding endpoints, all behind Session auth + role guards (viewer reads, admin
writes). Schema comes from Alembic; agent rows come from agent_store.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.platform.agent_lifecycle.credential_slots as credential_slots
import fleetent.platform.agent_lifecycle.secret_store as secret_store
import fleetent.platform.agent_management_console.agent_admin_api as api
import fleetent.platform.connector_management.agent_mcp_server_store as agent_mcp_server_store
import fleetent.platform.connector_management.agent_oauth_binding_store as agent_oauth_binding_store
import fleetent.platform.connector_management.connector_config_store as connector_config_store
import fleetent.platform.knowledge_base_management.agent_kbs_store as agent_kbs_store
import fleetent.platform.skill_management.skill_admin_store as skill_admin_store
import fleetent.user_store as user_store
from fleetent.db import create_database
from tests.integration._migration_template import apply_migrations


def _patch_all_stores(mp_or_monkeypatch, db_path: object) -> None:
    """Patch all platform stores that use Settings().database_url.

    These stores each have their own _database() that reads DATABASE_URL, which
    is deleted before every test by the autouse _isolate_database_url conftest
    fixture. Direct attribute patching bypasses that env-var dependency.
    """
    db_instance = create_database(f"sqlite:///{db_path}")
    mp_or_monkeypatch.setattr(user_store, "_db", lambda: db_instance)
    mp_or_monkeypatch.setattr(agent_store, "_db", lambda: db_instance)
    mp_or_monkeypatch.setattr(skill_admin_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(agent_kbs_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(agent_mcp_server_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(agent_oauth_binding_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(connector_config_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(credential_slots, "_database", lambda: db_instance)
    mp_or_monkeypatch.setattr(secret_store, "_database", lambda: db_instance)
    mp_or_monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Module-scoped client for 404/403 tests that don't create agents.

    Patches all platform store _database() functions directly to avoid conflicts
    with the autouse _isolate_database_url conftest fixture.
    """
    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("db_ro")
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    _patch_all_stores(mp, db_path)
    app = FastAPI()
    app.include_router(api.router)
    yield TestClient(app, raise_server_exceptions=True)
    mp.undo()


@pytest.fixture
def fresh_client(tmp_path, monkeypatch):
    """Function-scoped client for write tests that need a clean DB per test."""
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    _patch_all_stores(monkeypatch, db_path)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


# --- versions list ------------------------------------------------------------


def test_versions_requires_auth(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    assert fresh_client.get("/admin/agents/ops/versions").status_code == 401


def test_versions_viewer_can_read_desc_with_is_active(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    agent_store.create_version("ops", system_prompt="Ops v2.")
    token, _ = _session_for("viewer")

    resp = fresh_client.get("/admin/agents/ops/versions", headers=_hdr(token))
    assert resp.status_code == 200
    body = resp.json()
    assert [v["version"] for v in body] == [2, 1]
    active = [v for v in body if v["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == 2


# --- activate -----------------------------------------------------------------


def test_activate_admin_switches_active(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    agent_store.create_version("ops", system_prompt="Ops v2.")
    token, _ = _session_for("admin")

    resp = fresh_client.post("/admin/agents/ops/versions/1/activate", headers=_hdr(token))
    assert resp.status_code == 200
    versions = agent_store.list_versions("ops")
    active = next(v for v in versions if v.is_active)
    assert active.version == 1


def test_activate_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = fresh_client.post("/admin/agents/ops/versions/1/activate", headers=_hdr(token))
    assert resp.status_code == 403


def test_activate_unknown_version_404(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")
    resp = fresh_client.post("/admin/agents/ops/versions/99/activate", headers=_hdr(token))
    assert resp.status_code == 404


# --- bindings -----------------------------------------------------------------


def test_bind_and_unbind_user(fresh_client):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")

    resp = fresh_client.post("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 200
    bound = agent_store.get_agent_for_user("u-42")
    assert bound is not None and bound.id == agent.id

    resp = fresh_client.delete("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.get_agent_for_user("u-42") is None


def test_bind_user_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = fresh_client.post("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 403


def test_bind_and_unbind_channel_records_version(fresh_client):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")

    resp = fresh_client.post("/admin/agents/ops/bindings/channels/slack/C-1", headers=_hdr(token))
    assert resp.status_code == 200
    bound = agent_store.get_agent_for_channel("slack", "C-1")
    assert bound is not None and bound.id == agent.id
    assert agent_store.get_channel_bound_version_id("slack", "C-1") == agent.active_version_id

    resp = fresh_client.delete("/admin/agents/ops/bindings/channels/slack/C-1", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.get_agent_for_channel("slack", "C-1") is None


def test_bind_unknown_agent_404(client):
    token, _ = _session_for("admin")
    resp = client.post("/admin/agents/ghost/bindings/users/u-1", headers=_hdr(token))
    assert resp.status_code == 404


# --- bindings read ------------------------------------------------------------


def test_get_bindings_shape(fresh_client):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    agent_store.assign_user("u-1", agent.id)
    agent_store.assign_channel("slack", "C-1", agent.id)
    agent_store.bind_mcp_server(agent.id, "github")
    token, _ = _session_for("viewer")

    resp = fresh_client.get("/admin/agents/ops/bindings", headers=_hdr(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["users"] == ["u-1"]
    assert body["mcp_servers"] == ["github"]
    assert len(body["channels"]) == 1
    chan = body["channels"][0]
    assert chan["platform"] == "slack" and chan["channel_id"] == "C-1"


def test_get_bindings_unknown_agent_404(client):
    token, _ = _session_for("viewer")
    resp = client.get("/admin/agents/ghost/bindings", headers=_hdr(token))
    assert resp.status_code == 404


# --- agent-side skill bindings ------------------------------------------------


def test_put_and_get_agent_skill(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")

    resp = fresh_client.put(
        "/admin/agents/ops/skills/crm-ops", headers=_hdr(token), json={"enabled": True}
    )
    assert resp.status_code == 200

    resp = fresh_client.get("/admin/agents/ops/skills", headers=_hdr(token))
    assert resp.status_code == 200
    by_name = {s["skill_name"]: s["enabled"] for s in resp.json()}
    assert by_name.get("crm-ops") is True


def test_put_agent_skill_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = fresh_client.put(
        "/admin/agents/ops/skills/crm-ops", headers=_hdr(token), json={"enabled": True}
    )
    assert resp.status_code == 403


# --- agent MCP bindings -------------------------------------------------------


def test_bind_known_mcp_server(fresh_client, monkeypatch):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    monkeypatch.setattr(api, "_known_mcp_server_ids", lambda: {"github", "jira"})
    token, _ = _session_for("admin")

    resp = fresh_client.post("/admin/agents/ops/bindings/mcp/github", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.list_mcp_servers_for_agent(agent.id) == ["github"]

    resp = fresh_client.delete("/admin/agents/ops/bindings/mcp/github", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.list_mcp_servers_for_agent(agent.id) == []


def test_known_mcp_ids_include_store_registered(monkeypatch):
    # _known_mcp_server_ids uses DB-registered global servers, so a store-only
    # server is bindable.
    from fleetent.platform.connector_management import agent_mcp_server_store

    monkeypatch.setattr(
        agent_mcp_server_store,
        "list_mcp_servers",
        lambda agent_id: [{"server_id": "middle"}] if agent_id is None else [],
    )
    assert "middle" in api._known_mcp_server_ids()


def test_bind_store_registered_mcp_server(fresh_client, monkeypatch):
    from fleetent.platform.connector_management import agent_mcp_server_store

    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    monkeypatch.setattr(
        agent_mcp_server_store,
        "list_mcp_servers",
        lambda agent_id: [{"server_id": "middle"}] if agent_id is None else [],
    )
    token, _ = _session_for("admin")
    resp = fresh_client.post("/admin/agents/ops/bindings/mcp/middle", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    assert agent_store.list_mcp_servers_for_agent(agent.id) == ["middle"]


def test_bind_unknown_mcp_server_404(fresh_client, monkeypatch):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    monkeypatch.setattr(api, "_known_mcp_server_ids", lambda: {"github"})
    token, _ = _session_for("admin")

    resp = fresh_client.post("/admin/agents/ops/bindings/mcp/nope", headers=_hdr(token))
    assert resp.status_code == 404
    assert agent_store.list_mcp_servers_for_agent(agent.id) == []


def test_bind_mcp_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = fresh_client.post("/admin/agents/ops/bindings/mcp/github", headers=_hdr(token))
    assert resp.status_code == 403


# --- agent knowledge-base bindings -------------------------------------------


def _kb_ids(client, token):
    return client.get("/admin/agents/ops/kbs", headers=_hdr(token)).json()["kb_ids"]


def test_kb_bind_list_unbind(fresh_client):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    token, _ = _session_for("admin")
    assert _kb_ids(fresh_client, token) == []
    r = fresh_client.post("/admin/agents/ops/kbs", headers=_hdr(token), json={"kb_id": "kb1"})
    assert r.status_code == 200
    fresh_client.post(
        "/admin/agents/ops/kbs", headers=_hdr(token), json={"kb_id": "kb1"}
    )  # idempotent
    assert _kb_ids(fresh_client, token) == ["kb1"]
    assert fresh_client.delete("/admin/agents/ops/kbs/kb1", headers=_hdr(token)).status_code == 200
    assert _kb_ids(fresh_client, token) == []


def test_kb_bind_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    token, _ = _session_for("viewer")
    r = fresh_client.post("/admin/agents/ops/kbs", headers=_hdr(token), json={"kb_id": "kb1"})
    assert r.status_code == 403


def test_kb_bind_unknown_agent_404(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ghost/kbs", headers=_hdr(token), json={"kb_id": "kb1"})
    assert r.status_code == 404


# --- agent OAuth connector bindings ------------------------------------------


def _oauth_ids(client, token):
    r = client.get("/admin/agents/ops/bindings/oauth", headers=_hdr(token))
    return r.json()["connector_ids"]


def test_oauth_bind_list_unbind(fresh_client):
    from fleetent.platform.connector_management import connector_config_store

    agent_store.create_agent("ops", "Ops.", ["shell"])
    connector_config_store.add_connector("github", "GitHub")
    token, _ = _session_for("admin")
    assert _oauth_ids(fresh_client, token) == []
    r = fresh_client.post("/admin/agents/ops/bindings/oauth/github", headers=_hdr(token))
    assert r.status_code == 200
    assert _oauth_ids(fresh_client, token) == ["github"]
    d = fresh_client.delete("/admin/agents/ops/bindings/oauth/github", headers=_hdr(token))
    assert d.status_code == 200
    assert _oauth_ids(fresh_client, token) == []


def test_oauth_bind_unknown_connector_404(fresh_client):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    token, _ = _session_for("admin")
    r = fresh_client.post("/admin/agents/ops/bindings/oauth/nope", headers=_hdr(token))
    assert r.status_code == 404


def test_oauth_bind_viewer_forbidden(fresh_client):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    token, _ = _session_for("viewer")
    r = fresh_client.post("/admin/agents/ops/bindings/oauth/github", headers=_hdr(token))
    assert r.status_code == 403


# --- export agent.yaml --------------------------------------------------------


def test_export_agent_yaml(fresh_client):
    import yaml as _yaml

    from fleetent.platform.connector_management import agent_mcp_server_store

    agent = agent_store.create_agent(
        "support-bot",
        "You are support-bot.",
        ["search_*", "read_file"],
        plugins=["acme-docs", "billing"],
        features={"code_execution": True, "sandbox_env": {"TZ": "Asia/Shanghai"}},
        allowed_skills=["jira"],
        memory_namespace="support-bot",
    )
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        auth_type="bearer",
        api_key_env="ACME_DOCS_MCP_TOKEN",
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    agent_store.assign_user("u_alice", agent.id)
    agent_store.assign_channel("slack", "C0123ABCD", agent.id)

    token, _ = _session_for("admin")
    r = fresh_client.get("/admin/agents/support-bot/agent-yaml", headers=_hdr(token))
    assert r.status_code == 200, r.text
    doc = _yaml.safe_load(r.json()["yaml"])
    assert doc["name"] == "support-bot"
    assert doc["system_prompt"].startswith("You are support-bot")
    assert "model_overrides" not in doc
    assert doc["models"]["routes"]["default"][0]["target"] == "default"
    assert doc["allowed_tools"] == ["search_*", "read_file"]
    assert doc["plugins"] == ["acme-docs", "billing"]
    assert doc["features"]["sandbox_env"]["TZ"] == "Asia/Shanghai"
    assert doc["allowed_skills"] == ["jira"]
    assert doc["memory_namespace"] == "support-bot"
    assert {s["id"]: s for s in doc["mcp_servers"]}["docs"]["api_key_env"] == "ACME_DOCS_MCP_TOKEN"
    assert "slack:C0123ABCD" in doc["bindings"]["channels"]
    assert "u_alice" in doc["bindings"]["users"]


def test_export_agent_yaml_indentation(fresh_client):
    agent_store.create_agent(
        "fmt-bot",
        "line one\nline two\nline three",
        ["search_*", "read_file"],
    )
    token, _ = _session_for("admin")
    raw = fresh_client.get("/admin/agents/fmt-bot/agent-yaml", headers=_hdr(token)).json()["yaml"]
    # sequence items are indented two spaces under their key (not flush-left)
    assert "allowed_tools:\n  - search_*\n  - read_file" in raw
    # a multiline system prompt is a literal block scalar, not a quoted scalar
    assert "system_prompt: |" in raw
    assert "  line one\n  line two\n  line three" in raw


def test_export_agent_yaml_unknown_404(client):
    token, _ = _session_for("admin")
    r = client.get("/admin/agents/ghost/agent-yaml", headers=_hdr(token))
    assert r.status_code == 404


# --- deploy agent.yaml to the runtime agents dir ------------------------------


def test_deploy_writes_agent_yaml(fresh_client, tmp_path, monkeypatch):
    import yaml as _yaml

    home = tmp_path / "home"
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    agent_store.create_agent(
        "dep-bot",
        "You are dep-bot.",
        ["read_file"],
        plugins=["p1"],
    )
    token, _ = _session_for("admin")
    r = fresh_client.post("/admin/agents/dep-bot/deploy", headers=_hdr(token))
    assert r.status_code == 200, r.text
    dest = home / "agents" / "dep-bot" / "agent.yaml"
    assert dest.exists()
    assert r.json()["path"] == str(dest)
    doc = _yaml.safe_load(dest.read_text())
    assert doc["name"] == "dep-bot"
    assert "models" in doc
    assert "model_overrides" not in doc
    assert doc["allowed_tools"] == ["read_file"]
    assert doc["plugins"] == ["p1"]

    # redeploy overwrites in place after an edit
    agent_store.create_version("dep-bot", system_prompt="changed")
    r2 = fresh_client.post("/admin/agents/dep-bot/deploy", headers=_hdr(token))
    assert r2.status_code == 200
    assert "changed" in dest.read_text()


def test_deploy_viewer_forbidden(fresh_client):
    agent_store.create_agent("dep2", "x", [])
    token, _ = _session_for("viewer")
    r = fresh_client.post("/admin/agents/dep2/deploy", headers=_hdr(token))
    assert r.status_code == 403


def test_deploy_unknown_agent_404(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ghost/deploy", headers=_hdr(token))
    assert r.status_code == 404
