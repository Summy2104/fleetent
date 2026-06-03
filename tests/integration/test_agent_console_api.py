"""Tests for agent_console_api (/admin/agents). Covers platform.md scenarios 36-46
(the management-face additions: enable/disable, archive+protection, clone, templates,
observability, provenance — CRUD/versioning belong to multi-agent-management)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_store as store
import fleetent.platform.agent_management_console.agent_console_api as api
import fleetent.user_store as user_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    # no references and no agent defs by default; tests override
    monkeypatch.setattr(api, "references_for", lambda name: {"users": [], "channels": []})
    monkeypatch.setattr(api, "get_agent_def", lambda name: None)
    monkeypatch.setattr(api, "create_agent_def", lambda n, sp, at: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


# --- role guards (场景 46) ----------------------------------------------------


def test_no_auth_401(client):
    assert client.get("/admin/agents").status_code == 401


def test_viewer_can_read_not_write(client):
    token, _ = _session_for("viewer")
    assert client.get("/admin/agents", headers=_hdr(token)).status_code == 200
    assert client.post("/admin/agents/ops/disable", headers=_hdr(token)).status_code == 403


# --- enable/disable (场景 39) -------------------------------------------------


def test_disable_then_enable(client):
    token, _ = _session_for("admin")
    client.post("/admin/agents/ops/disable", headers=_hdr(token))
    assert store.get_state("ops")["status"] == "disabled"
    client.post("/admin/agents/ops/enable", headers=_hdr(token))
    assert store.get_state("ops")["status"] == "enabled"
    assert any(a["action"] == "agent.disable" for a in audit.search_audit())


# --- archive + binding protection + restore (场景 40/41) ---------------------


def test_archive_blocked_when_bound(client, monkeypatch):
    monkeypatch.setattr(
        api, "references_for", lambda name: {"users": ["u1"], "channels": ["slack:C1"]}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/archive", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert "u1" in r.json()["detail"]["users"]
    assert store.get_state("ops")["status"] != "archived"


def test_archive_requires_confirm_then_restore(client):
    token, _ = _session_for("admin")
    assert client.post("/admin/agents/ops/archive", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/agents/ops/archive", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert store.get_state("ops")["status"] == "archived"
    client.post("/admin/agents/ops/restore", headers=_hdr(token))
    assert store.get_state("ops")["status"] == "enabled"


# --- clone (场景 42) ----------------------------------------------------------


def test_clone_copies_def_no_bindings(client, monkeypatch):
    created = {}
    monkeypatch.setattr(
        api,
        "get_agent_def",
        lambda name: (
            {"id": 1, "system_prompt": "p", "allowed_tools": ["read_*"]} if name == "ops" else None
        ),
    )
    monkeypatch.setattr(
        api, "create_agent_def", lambda n, sp, at: created.update(name=n, sp=sp, at=at)
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/clone", headers=_hdr(token), json={"new_name": "ops2"})
    assert r.status_code == 200
    assert created == {"name": "ops2", "sp": "p", "at": ["read_*"]}
    assert store.get_state("ops2")["provenance"] == "adhoc"


def test_clone_duplicate_name_rejected(client, monkeypatch):
    monkeypatch.setattr(
        api, "get_agent_def", lambda name: {"id": 1, "system_prompt": "p", "allowed_tools": []}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/clone", headers=_hdr(token), json={"new_name": "exists"})
    assert r.status_code == 409


# --- templates (场景 43) ------------------------------------------------------


def test_templates_listed(client):
    token, _ = _session_for("viewer")
    r = client.get("/admin/agent-templates", headers=_hdr(token))
    ids = {t["id"] for t in r.json()}
    assert {"readonly-qa", "ops", "support"} <= ids


# --- observability (场景 45) --------------------------------------------------


def test_observability_view(client, monkeypatch):
    monkeypatch.setattr(
        api, "agent_observability_agg", lambda name, window: {"agent_name": name, "calls": 42}
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/agents/ops/observability", headers=_hdr(token))
    assert r.json()["calls"] == 42


# --- full CRUD: create / read-full / update / delete --------------------------


def _wire_real_store(monkeypatch):
    """Wire the console seams to the real agent_store (mirrors server.py wiring)."""

    def _def(name):
        a = agent_store.get_by_name(name)
        if a is None:
            return None
        return {"id": a.id, "system_prompt": a.system_prompt, "allowed_tools": a.allowed_tools}

    def _update(name, system_prompt, allowed_tools):
        kwargs = {}
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        if allowed_tools is not None:
            kwargs["allowed_tools"] = allowed_tools
        agent_store.create_version(name, **kwargs)

    def _refs(name):
        a = agent_store.get_by_name(name)
        return store.references(a.id) if a else {"users": [], "channels": []}

    monkeypatch.setattr(api, "get_agent_def", _def)
    monkeypatch.setattr(
        api, "create_agent_def", lambda n, sp, at: agent_store.create_agent(n, sp, at)
    )
    monkeypatch.setattr(api, "update_agent_def", _update)
    monkeypatch.setattr(api, "delete_agent_def", lambda n: agent_store.delete_agent(n))
    monkeypatch.setattr(api, "references_for", _refs)


def test_create_agent_persists_and_lists(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "newbot", "system_prompt": "hi", "allowed_tools": ["shell"]},
    )
    assert r.status_code == 201
    found = agent_store.get_by_name("newbot")
    assert found is not None and found.system_prompt == "hi"
    st = store.get_state("newbot")
    assert st["provenance"] == "adhoc" and st["status"] == "enabled"
    assert "newbot" in {a["agent_name"] for a in store.list_states()}


def test_create_duplicate_name_409(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("dup", "p", [])
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents", headers=_hdr(token), json={"name": "dup", "system_prompt": "x"}
    )
    assert r.status_code == 409


def test_create_viewer_forbidden(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/agents", headers=_hdr(token), json={"name": "nope", "system_prompt": "x"}
    )
    assert r.status_code == 403
    assert agent_store.get_by_name("nope") is None


def test_get_full_definition(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "Ops prompt", ["read_*"])
    token, _ = _session_for("viewer")
    r = client.get("/admin/agents/ops", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "Ops prompt"
    assert r.json()["allowed_tools"] == ["read_*"]


def test_get_missing_404(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("viewer")
    assert client.get("/admin/agents/ghost", headers=_hdr(token)).status_code == 404


def test_patch_creates_new_active_version(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "v1", ["shell"])
    token, _ = _session_for("admin")
    r = client.patch("/admin/agents/ops", headers=_hdr(token), json={"system_prompt": "v2"})
    assert r.status_code == 200
    assert agent_store.get_by_name("ops").system_prompt == "v2"
    assert len(agent_store.list_versions("ops")) == 2


def test_patch_missing_404(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.patch("/admin/agents/ghost", headers=_hdr(token), json={"system_prompt": "x"})
    assert r.status_code == 404


def test_patch_managed_marks_drift(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "v1", ["shell"])
    store.set_provenance("ops", "managed")
    token, _ = _session_for("admin")
    client.patch("/admin/agents/ops", headers=_hdr(token), json={"system_prompt": "v2"})
    assert store.get_state("ops")["drift"] == 1


def test_delete_requires_confirm(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", [])
    token, _ = _session_for("admin")
    r = client.delete("/admin/agents/ops", headers=_hdr(token))
    assert r.status_code == 428
    assert agent_store.get_by_name("ops") is not None


def test_delete_blocked_when_bound(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", [])
    monkeypatch.setattr(api, "references_for", lambda name: {"users": ["u1"], "channels": []})
    token, _ = _session_for("admin")
    r = client.delete("/admin/agents/ops", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert agent_store.get_by_name("ops") is not None


def test_delete_removes_def_and_state(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", [])
    store.enable("ops")
    token, _ = _session_for("admin")
    r = client.delete("/admin/agents/ops", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert agent_store.get_by_name("ops") is None
    assert all(a["agent_name"] != "ops" for a in store.list_states())


def test_delete_viewer_forbidden(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", [])
    token, _ = _session_for("viewer")
    r = client.delete("/admin/agents/ops", headers=_hdr(token, confirm=True))
    assert r.status_code == 403
