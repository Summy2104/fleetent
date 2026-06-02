"""Tests for agent_admin_api (/admin/agents version + binding REST).

Covers multi-agent-management tasks 11.1/11.3: version listing + activation and the
four binding endpoints, all behind Session auth + role guards (viewer reads, admin
writes). Schema comes from Alembic; agent rows come from agent_store.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.audit_log as audit
import fleetent.auth as auth
import fleetent.platform.agent_management_console.agent_admin_api as api
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


def test_versions_requires_auth(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    assert client.get("/admin/agents/ops/versions").status_code == 401


def test_versions_viewer_can_read_desc_with_is_active(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    agent_store.create_version("ops", system_prompt="Ops v2.")
    token, _ = _session_for("viewer")

    resp = client.get("/admin/agents/ops/versions", headers=_hdr(token))
    assert resp.status_code == 200
    body = resp.json()
    assert [v["version"] for v in body] == [2, 1]
    active = [v for v in body if v["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == 2


# --- activate -----------------------------------------------------------------


def test_activate_admin_switches_active(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    agent_store.create_version("ops", system_prompt="Ops v2.")
    token, _ = _session_for("admin")

    resp = client.post("/admin/agents/ops/versions/1/activate", headers=_hdr(token))
    assert resp.status_code == 200
    versions = agent_store.list_versions("ops")
    active = next(v for v in versions if v.is_active)
    assert active.version == 1


def test_activate_viewer_forbidden(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = client.post("/admin/agents/ops/versions/1/activate", headers=_hdr(token))
    assert resp.status_code == 403


def test_activate_unknown_version_404(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")
    resp = client.post("/admin/agents/ops/versions/99/activate", headers=_hdr(token))
    assert resp.status_code == 404


# --- bindings -----------------------------------------------------------------


def test_bind_and_unbind_user(client):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")

    resp = client.post("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 200
    bound = agent_store.get_agent_for_user("u-42")
    assert bound is not None and bound.id == agent.id

    resp = client.delete("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.get_agent_for_user("u-42") is None


def test_bind_user_viewer_forbidden(client):
    agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("viewer")
    resp = client.post("/admin/agents/ops/bindings/users/u-42", headers=_hdr(token))
    assert resp.status_code == 403


def test_bind_and_unbind_channel_records_version(client):
    agent = agent_store.create_agent("ops", "Ops v1.", ["shell"])
    token, _ = _session_for("admin")

    resp = client.post("/admin/agents/ops/bindings/channels/slack/C-1", headers=_hdr(token))
    assert resp.status_code == 200
    bound = agent_store.get_agent_for_channel("slack", "C-1")
    assert bound is not None and bound.id == agent.id
    assert agent_store.get_channel_bound_version_id("slack", "C-1") == agent.active_version_id

    resp = client.delete("/admin/agents/ops/bindings/channels/slack/C-1", headers=_hdr(token))
    assert resp.status_code == 200
    assert agent_store.get_agent_for_channel("slack", "C-1") is None


def test_bind_unknown_agent_404(client):
    token, _ = _session_for("admin")
    resp = client.post("/admin/agents/ghost/bindings/users/u-1", headers=_hdr(token))
    assert resp.status_code == 404
