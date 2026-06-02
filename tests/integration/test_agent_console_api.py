"""Tests for agent_console_api (/admin/agents). Covers platform.md scenarios 36-46
(the management-face additions: enable/disable, archive+protection, clone, templates,
observability, provenance — CRUD/versioning belong to multi-agent-management)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
