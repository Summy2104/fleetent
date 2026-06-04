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
        api,
        "create_agent_def",
        lambda n, sp, at, *a, **k: created.update(name=n, sp=sp, at=at),
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


def test_template_create(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agent-templates",
        headers=_hdr(token),
        json={
            "id": "triage",
            "display_name": "Triage",
            "allowed_tools": ["read_*"],
            "system_prompt": "You triage.",
        },
    )
    assert r.status_code == 201
    ids = {t["id"] for t in client.get("/admin/agent-templates", headers=_hdr(token)).json()}
    assert "triage" in ids
    assert any(a["action"] == "template.create" for a in audit.search_audit())


def test_template_create_duplicate_409(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agent-templates", headers=_hdr(token), json={"id": "ops", "display_name": "Dup"}
    )
    assert r.status_code == 409


def test_template_create_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/agent-templates", headers=_hdr(token), json={"id": "x", "display_name": "X"}
    )
    assert r.status_code == 403


def test_template_edit(client):
    token, _ = _session_for("admin")
    r = client.patch(
        "/admin/agent-templates/ops", headers=_hdr(token), json={"system_prompt": "v2"}
    )
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "v2"
    assert r.json()["allowed_tools"] == ["read_*", "exec_*", "github__*"]


def test_template_edit_missing_404(client):
    token, _ = _session_for("admin")
    r = client.patch(
        "/admin/agent-templates/ghost", headers=_hdr(token), json={"display_name": "x"}
    )
    assert r.status_code == 404


def test_template_delete(client):
    token, _ = _session_for("admin")
    r = client.delete("/admin/agent-templates/support", headers=_hdr(token))
    assert r.status_code == 200
    ids = {t["id"] for t in client.get("/admin/agent-templates", headers=_hdr(token)).json()}
    assert "support" not in ids


def test_template_delete_missing_404(client):
    token, _ = _session_for("admin")
    assert client.delete("/admin/agent-templates/ghost", headers=_hdr(token)).status_code == 404


def test_template_delete_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    assert client.delete("/admin/agent-templates/ops", headers=_hdr(token)).status_code == 403


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
        return {
            "id": a.id,
            "system_prompt": a.system_prompt,
            "allowed_tools": a.allowed_tools,
            "skills_dir": a.skills_dir,
            "mcp_server_ids": a.mcp_server_ids,
            "model_overrides": a.model_overrides,
            "memory_namespace": a.memory_namespace,
            "template_id": a.template_id,
        }

    def _create(name, sp, at, sd=None, mids=None, mo=None, mn="default", template_id=None):
        agent_store.create_agent(
            name,
            sp,
            at,
            skills_dir=sd,
            mcp_server_ids=mids,
            model_overrides=mo,
            memory_namespace=mn,
            template_id=template_id,
        )

    def _update(name, system_prompt, allowed_tools, sd=None, mids=None, mo=None, mn=None):
        kwargs = {}
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        if allowed_tools is not None:
            kwargs["allowed_tools"] = allowed_tools
        if sd is not None:
            kwargs["skills_dir"] = sd
        if mids is not None:
            kwargs["mcp_server_ids"] = mids
        if mo is not None:
            kwargs["model_overrides"] = mo
        if mn is not None:
            kwargs["memory_namespace"] = mn
        agent_store.create_version(name, **kwargs)

    def _refs(name):
        a = agent_store.get_by_name(name)
        return store.references(a.id) if a else {"users": [], "channels": []}

    monkeypatch.setattr(api, "get_agent_def", _def)
    monkeypatch.setattr(api, "create_agent_def", _create)
    monkeypatch.setattr(api, "update_agent_def", _update)
    monkeypatch.setattr(api, "delete_agent_def", lambda n: agent_store.delete_agent(n))
    monkeypatch.setattr(api, "references_for", _refs)


def test_create_agent_persists_and_lists(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={
            "name": "newbot",
            "system_prompt": "hi",
            "allowed_tools": ["shell"],
            "template_id": "ops",
        },
    )
    assert r.status_code == 201
    found = agent_store.get_by_name("newbot")
    assert found is not None and found.system_prompt == "hi"
    st = store.get_state("newbot")
    assert st["provenance"] == "adhoc" and st["status"] == "enabled"
    assert "newbot" in {a["agent_name"] for a in store.list_states()}


def test_create_requires_template_id_422(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "notmpl", "system_prompt": "x", "allowed_tools": []},
    )
    assert r.status_code == 422
    assert agent_store.get_by_name("notmpl") is None


def test_create_unknown_template_id_404(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "ghosttmpl", "system_prompt": "x", "template_id": "nope"},
    )
    assert r.status_code == 404
    assert agent_store.get_by_name("ghosttmpl") is None


def test_create_persists_template_id_and_echoes(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "linked", "system_prompt": "hi", "template_id": "support"},
    )
    assert r.status_code == 201
    assert r.json()["template_id"] == "support"
    assert agent_store.get_by_name("linked").template_id == "support"
    g = client.get("/admin/agents/linked", headers=_hdr(token))
    assert g.json()["template_id"] == "support"


def test_create_duplicate_name_409(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("dup", "p", [])
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "dup", "system_prompt": "x", "template_id": "ops"},
    )
    assert r.status_code == 409


def test_create_viewer_forbidden(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "nope", "system_prompt": "x", "template_id": "ops"},
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


# --- version-config fields (skills_dir / mcp_server_ids / model_overrides / memory_namespace) ---


def test_create_persists_version_config_fields(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={
            "name": "cfgbot",
            "system_prompt": "hi",
            "allowed_tools": ["shell"],
            "skills_dir": "/s",
            "mcp_server_ids": ["github"],
            "model_overrides": {"model": "x"},
            "memory_namespace": "team",
            "template_id": "ops",
        },
    )
    assert r.status_code == 201
    a = agent_store.get_by_name("cfgbot")
    assert a.skills_dir == "/s"
    assert a.mcp_server_ids == ["github"]
    assert a.model_overrides == {"model": "x"}
    assert a.memory_namespace == "team"


def test_get_returns_version_config_fields(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent(
        "cfgbot",
        "p",
        ["shell"],
        skills_dir="/s",
        mcp_server_ids=["github"],
        model_overrides={"model": "x"},
        memory_namespace="team",
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/agents/cfgbot", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["skills_dir"] == "/s"
    assert body["mcp_server_ids"] == ["github"]
    assert body["model_overrides"] == {"model": "x"}
    assert body["memory_namespace"] == "team"


def test_patch_overrides_only_provided_field(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("cfgbot", "v1", ["shell"], skills_dir="/s")
    token, _ = _session_for("admin")
    r = client.patch("/admin/agents/cfgbot", headers=_hdr(token), json={"memory_namespace": "team"})
    assert r.status_code == 200
    a = agent_store.get_by_name("cfgbot")
    assert a.memory_namespace == "team"
    assert a.skills_dir == "/s"  # inherited from prior version


def test_clone_copies_version_config_fields(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent(
        "src",
        "p",
        ["shell"],
        skills_dir="/s",
        mcp_server_ids=["github"],
        model_overrides={"model": "x"},
        memory_namespace="team",
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/src/clone", headers=_hdr(token), json={"new_name": "dst"})
    assert r.status_code == 200
    a = agent_store.get_by_name("dst")
    assert a.skills_dir == "/s"
    assert a.mcp_server_ids == ["github"]
    assert a.model_overrides == {"model": "x"}
    assert a.memory_namespace == "team"
