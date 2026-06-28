"""Tests for agent_console_api (/admin/agents)."""

import pytest
import yaml
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_store as store
import fleetent.platform.agent_management_console.agent_console_api as api
import fleetent.user_store as user_store
from fleetent.platform.node_management import node_store, placement_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # no references and no agent defs by default; tests override
    monkeypatch.setattr(api, "references_for", lambda name: {"users": [], "channels": []})
    monkeypatch.setattr(api, "get_agent_def", lambda name: None)
    monkeypatch.setattr(api, "create_agent_def", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
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


def test_disable_then_enable(client, monkeypatch):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    _wire_real_store(monkeypatch)
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    # enable now requires a node binding, so pin one for the round-trip
    node = _seed_node(monkeypatch)
    placement_store.pin_agent(ops.id, node)
    token, _ = _session_for("admin")
    client.post("/admin/agents/ops/disable", headers=_hdr(token))
    assert store.get_state(ops.id)["status"] == "disabled"
    client.post("/admin/agents/ops/enable", headers=_hdr(token))
    assert store.get_state(ops.id)["status"] == "enabled"
    assert any(a["action"] == "agent.disable" for a in audit.search_audit())


# --- dual-state query: runtime + placement projection ------------------------


def test_list_merges_runtime_and_placement(client, monkeypatch):
    _wire_real_store(monkeypatch)
    node = _seed_node(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    store.enable(ops.id)  # admin_state row so the agent shows in list_states()
    placement_store.pin_agent(ops.id, node, pinned_by="admin")
    node_store.upsert_agent_status(ops.id, node_id=node, phase="running", pid=999, health="ok")
    token, _ = _session_for("admin")

    rows = client.get("/admin/agents", headers=_hdr(token)).json()
    row = next(r for r in rows if r["agent_name"] == "ops")

    assert row["status"] == "enabled"
    assert set(row["runtime"]) == {"phase", "health", "pid", "node_id", "reported_at"}
    assert row["runtime"]["phase"] == "running"
    assert row["runtime"]["health"] == "ok"
    assert row["runtime"]["pid"] == 999
    assert row["runtime"]["node_id"] == node
    assert row["runtime"]["reported_at"]
    assert set(row["placement"]) == {"node_id", "pinned_at", "pinned_by"}
    assert row["placement"]["node_id"] == node
    assert row["placement"]["pinned_by"] == "admin"
    assert row["placement"]["pinned_at"]


def test_list_null_runtime_placement_when_absent(client, monkeypatch):
    _wire_real_store(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    store.enable(ops.id)  # admin_state row so the agent shows in list_states()
    token, _ = _session_for("admin")

    rows = client.get("/admin/agents", headers=_hdr(token)).json()
    row = next(r for r in rows if r["agent_name"] == "ops")

    assert row["runtime"] is None
    assert row["placement"] is None


def test_detail_merges_runtime_and_placement(client, monkeypatch):
    _wire_real_store(monkeypatch)
    node = _seed_node(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops prompt", ["read_*"])
    placement_store.pin_agent(ops.id, node)
    node_store.upsert_agent_status(ops.id, node_id=node, phase="running", pid=7, health="ok")
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/ops", headers=_hdr(token)).json()

    assert body["runtime"]["phase"] == "running"
    assert body["runtime"]["node_id"] == node
    assert body["placement"]["node_id"] == node
    # merge must not clobber existing definition fields
    assert body["agent"] == "ops"
    assert body["system_prompt"] == "Ops prompt"
    assert body["allowed_tools"] == ["read_*"]


def test_runtime_and_placement_are_independent(client, monkeypatch):
    """Asymmetric combos: pinned-without-status and status-without-pin."""
    _wire_real_store(monkeypatch)
    node = _seed_node(monkeypatch)
    pinned = agent_store.create_agent("pinned", "p", ["shell"])
    store.enable(pinned.id)
    placement_store.pin_agent(pinned.id, node)  # bound but no status reported
    running = agent_store.create_agent("running", "p", ["shell"])
    store.enable(running.id)
    node_store.upsert_agent_status(running.id, node_id=node, phase="running")  # status, no pin
    token, _ = _session_for("admin")

    rows = {r["agent_name"]: r for r in client.get("/admin/agents", headers=_hdr(token)).json()}

    assert rows["pinned"]["runtime"] is None
    assert rows["pinned"]["placement"]["node_id"] == node
    assert rows["running"]["runtime"]["phase"] == "running"
    assert rows["running"]["placement"] is None


def test_detail_null_placement_when_unbound(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "Ops.", ["shell"])
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/ops", headers=_hdr(token)).json()

    assert body["runtime"] is None
    assert body["placement"] is None


def test_detail_includes_config_overrides_yaml(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "Ops.", ["shell"])
    overrides = {"im": {"slack": {"bot_token_env": "SLACK_BOT_TOKEN"}}}
    agent_store.set_config_overrides("ops", overrides)
    token, _ = _session_for("viewer")

    body = client.get("/admin/agents/ops", headers=_hdr(token)).json()

    assert body["config_overrides"] == overrides
    assert yaml.safe_load(body["config_overrides_yaml"]) == overrides


# --- default disabled on create / clone --------------------------------------


def test_create_defaults_disabled(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "newbot", "system_prompt": "hi", "allowed_tools": ["shell"]},
    )
    assert r.status_code == 201
    created = agent_store.get_by_name("newbot")
    assert created is not None
    assert store.get_state(created.id)["status"] == "disabled"
    assert r.json()["status"] == "disabled"


def test_clone_defaults_disabled(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", ["read_*"])
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/clone", headers=_hdr(token), json={"new_name": "ops2"})
    assert r.status_code == 200
    clone = agent_store.get_by_name("ops2")
    assert clone is not None
    assert store.get_state(clone.id)["status"] == "disabled"


# --- enable guard: must be bound to a node -----------------------------------


def test_enable_rejected_when_not_bound(client, monkeypatch):
    _wire_real_store(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    store.disable(ops.id)
    token, _ = _session_for("admin")

    r = client.post("/admin/agents/ops/enable", headers=_hdr(token))

    assert r.status_code == 409
    assert "agent not bound to a node" in str(r.json()["detail"])
    assert store.get_state(ops.id)["status"] == "disabled"
    assert not any(a["action"] == "agent.enable" for a in audit.search_audit())


def test_enable_succeeds_when_bound(client, monkeypatch):
    _wire_real_store(monkeypatch)
    node = _seed_node(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    store.disable(ops.id)
    placement_store.pin_agent(ops.id, node)
    token, _ = _session_for("admin")

    r = client.post("/admin/agents/ops/enable", headers=_hdr(token))

    assert r.status_code == 200
    assert store.get_state(ops.id)["status"] == "enabled"
    assert any(a["action"] == "agent.enable" for a in audit.search_audit())


def test_disable_not_gated_by_binding(client, monkeypatch):
    _wire_real_store(monkeypatch)
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    store.enable(ops.id)  # enabled but never pinned
    token, _ = _session_for("admin")

    r = client.post("/admin/agents/ops/disable", headers=_hdr(token))

    assert r.status_code == 200
    assert store.get_state(ops.id)["status"] == "disabled"


# --- archive + binding protection + restore (场景 40/41) ---------------------


def test_archive_blocked_when_bound(client, monkeypatch):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    _wire_real_store(monkeypatch)
    monkeypatch.setattr(api, "references_for", lambda name: {"users": ["u1"], "channels": []})
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/archive", headers=_hdr(token, confirm=True))
    assert r.status_code == 409
    assert "u1" in r.json()["detail"]["users"]
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    assert store.get_state(ops.id)["status"] != "archived"


def test_archive_requires_confirm_then_restore(client, monkeypatch):
    agent_store.create_agent("ops", "Ops.", ["shell"])
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    assert client.post("/admin/agents/ops/archive", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/agents/ops/archive", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    assert store.get_state(ops.id)["status"] == "archived"
    client.post("/admin/agents/ops/restore", headers=_hdr(token))
    assert store.get_state(ops.id)["status"] == "enabled"


# --- clone (场景 42) ----------------------------------------------------------


def test_clone_copies_def_no_bindings(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "p", ["read_*"])
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/clone", headers=_hdr(token), json={"new_name": "ops2"})
    assert r.status_code == 200
    clone = agent_store.get_by_name("ops2")
    assert clone is not None
    assert clone.system_prompt == "p"
    assert clone.allowed_tools == ["read_*"]
    assert store.get_state(clone.id)["status"] == "disabled"


def test_clone_duplicate_name_rejected(client, monkeypatch):
    monkeypatch.setattr(
        api, "get_agent_def", lambda name: {"id": 1, "system_prompt": "p", "allowed_tools": []}
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/agents/ops/clone", headers=_hdr(token), json={"new_name": "exists"})
    assert r.status_code == 409


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
            "tenant_id": a.tenant_id,
            "team_id": a.team_id,
            "system_prompt": a.system_prompt,
            "allowed_tools": a.allowed_tools,
            "skills_dir": a.skills_dir,
            "mcp_server_ids": a.mcp_server_ids,
            "model_overrides": a.model_overrides,
            "memory_namespace": a.memory_namespace,
            "icon": a.icon,
            "config_overrides": a.config_overrides,
            "supports_dm": a.supports_dm,
            "supports_groups": a.supports_groups,
        }

    def _create(
        name,
        sp,
        at,
        sd=None,
        mids=None,
        mo=None,
        mn="default",
        plugins=None,
        features=None,
        icon=None,
        tenant_id="default",
        team_id=None,
        config_overrides=None,
    ):
        agent_store.create_agent(
            name,
            sp,
            at,
            plugins=plugins,
            features=features,
            skills_dir=sd,
            mcp_server_ids=mids,
            model_overrides=mo,
            memory_namespace=mn,
            icon=icon,
            tenant_id=tenant_id,
            team_id=team_id,
            config_overrides=config_overrides,
        )

    def _update(
        name,
        system_prompt,
        allowed_tools,
        sd=None,
        mids=None,
        mo=None,
        mn=None,
        tenant_id=None,
        team_id=None,
        config_overrides=None,
    ):
        if tenant_id is not None or team_id is not None:
            cur = agent_store.get_by_name(name)
            if cur is not None:
                agent_store.set_identity(
                    name,
                    tenant_id if tenant_id is not None else cur.tenant_id,
                    team_id if team_id is not None else cur.team_id,
                )
        kwargs = {}
        if config_overrides is not None:
            kwargs["config_overrides"] = config_overrides
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
        if kwargs:
            agent_store.update_agent_config(name, **kwargs)

    def _refs(name):
        a = agent_store.get_by_name(name)
        return store.references(a.id) if a else {"users": [], "channels": []}

    monkeypatch.setattr(api, "get_agent_def", _def)
    monkeypatch.setattr(api, "create_agent_def", _create)
    monkeypatch.setattr(api, "update_agent_def", _update)
    monkeypatch.setattr(api, "delete_agent_def", lambda n: agent_store.delete_agent(n))

    monkeypatch.setattr(api, "references_for", _refs)
    monkeypatch.setattr(api, "set_agent_icon", agent_store.set_icon)
    monkeypatch.setattr(api, "agent_icons", agent_store.icons_by_name)

    # Dual-state read seams wired to the real node_management stores (mirrors server.py).
    # raising=False keeps this forward-compatible while the seams are being introduced.
    monkeypatch.setattr(api, "get_agent_runtime", node_store.get_agent_status, raising=False)
    monkeypatch.setattr(api, "get_agent_placement", placement_store.get_for_agent, raising=False)
    monkeypatch.setattr(api, "list_agent_runtimes", node_store.list_agent_status, raising=False)
    monkeypatch.setattr(
        api, "list_agent_placements", placement_store.list_placements, raising=False
    )


def _seed_node(monkeypatch, node_id: str = "node-a") -> str:
    """Register a node (needs a master key) so placements/status can reference it."""
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    node_store.register_node(node_id)
    return node_id


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
        },
    )
    assert r.status_code == 201
    found = agent_store.get_by_name("newbot")
    assert found is not None and found.system_prompt == "hi"
    st = store.get_state(found.id)
    # New agents default to disabled (must be pinned to a node before enable).
    assert st["status"] == "disabled"
    assert "newbot" in {a["agent_name"] for a in store.list_states()}


def test_create_with_model_overrides_and_capabilities_yaml(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    yaml_blob = (
        "allowed_tools:\n  - search_*\n  - read_file\n"
        "plugins:\n  - acme-docs\n  - billing\n"
        "features:\n  code_execution: true\n  sandbox_env:\n    TZ: Asia/Shanghai\n"
    )
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={
            "name": "capbot",
            "system_prompt": "You are ops.",
            "model_overrides": {
                "default": {"provider": "anthropic", "model": "claude-opus-4-8"},
                "fast": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
                "reasoning": {
                    "provider": "openai-compatible",
                    "model": "deepseek-r1",
                    "base_url_env": "DEEPSEEK_BASE_URL",
                },
            },
            "capabilities_yaml": yaml_blob,
        },
    )
    assert r.status_code == 201, r.text
    a = agent_store.get_by_name("capbot")
    assert a.allowed_tools == ["search_*", "read_file"]
    assert a.plugins == ["acme-docs", "billing"]
    assert a.features["code_execution"] is True
    assert a.features["sandbox_env"]["TZ"] == "Asia/Shanghai"
    assert a.model_overrides["default"]["model"] == "claude-opus-4-8"
    assert a.model_overrides["reasoning"]["base_url_env"] == "DEEPSEEK_BASE_URL"


def test_create_bad_capabilities_yaml_422(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={
            "name": "badyaml",
            "capabilities_yaml": "allowed_tools: [unterminated",
        },
    )
    assert r.status_code == 422
    assert agent_store.get_by_name("badyaml") is None


def test_create_duplicate_name_409(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("dup", "p", [])
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "dup", "system_prompt": "x"},
    )
    assert r.status_code == 409


def test_create_viewer_forbidden(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "nope", "system_prompt": "x"},
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


def test_get_surfaces_im_capabilities(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "Ops prompt", ["read_*"])
    agent_store.set_im_capabilities("ops", supports_dm=True, supports_groups=True)
    token, _ = _session_for("viewer")
    r = client.get("/admin/agents/ops", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["supports_dm"] is True
    assert body["supports_groups"] is True


def test_get_missing_404(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("viewer")
    assert client.get("/admin/agents/ghost", headers=_hdr(token)).status_code == 404


def test_patch_updates_current_config_and_bumps_version(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "v1", ["shell"])
    token, _ = _session_for("admin")
    r = client.patch("/admin/agents/ops", headers=_hdr(token), json={"system_prompt": "v2"})
    assert r.status_code == 200
    updated = agent_store.get_by_name("ops")
    assert updated is not None
    assert updated.system_prompt == "v2"
    assert updated.version == 2


def test_patch_capabilities_yaml_updates_tools(client, monkeypatch):
    _wire_real_store(monkeypatch)
    agent_store.create_agent("ops", "v1", ["shell"])
    token, _ = _session_for("admin")
    r = client.patch(
        "/admin/agents/ops",
        headers=_hdr(token),
        json={"capabilities_yaml": "allowed_tools:\n  - search_*\n  - read_file\n"},
    )
    assert r.status_code == 200, r.text
    assert agent_store.get_by_name("ops").allowed_tools == ["search_*", "read_file"]


def test_patch_missing_404(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.patch("/admin/agents/ghost", headers=_hdr(token), json={"system_prompt": "x"})
    assert r.status_code == 404


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
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    store.enable(ops.id)
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


def test_create_with_icon_and_list_includes_it(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents",
        headers=_hdr(token),
        json={"name": "iconbot", "system_prompt": "x", "icon": "🦊"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["icon"] == "🦊"
    assert agent_store.get_by_name("iconbot").icon == "🦊"
    # list view carries the icon for the card grid
    rows = client.get("/admin/agents", headers=_hdr(token)).json()
    assert {x["agent_name"]: x.get("icon") for x in rows}["iconbot"] == "🦊"


def test_update_changes_icon(client, monkeypatch):
    _wire_real_store(monkeypatch)
    token, _ = _session_for("admin")
    agent_store.create_agent("ic2", "p", [], icon="🐱")
    r = client.patch("/admin/agents/ic2", headers=_hdr(token), json={"icon": "🐶"})
    assert r.status_code == 200
    assert agent_store.get_by_name("ic2").icon == "🐶"
    assert r.json()["icon"] == "🐶"
