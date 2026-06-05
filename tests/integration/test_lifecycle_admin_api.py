"""Admin start/stop/status endpoints for agent runtime processes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.user_store as us
from fleetent.platform.agent_lifecycle import controller, lifecycle_admin_api, materialize


class _FakeProc:
    def __init__(self):
        self.pid = 321
        self._rc = None

    def poll(self):
        return self._rc

    def terminate(self):
        self._rc = -15


def _migrate(db_path):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(us, "DB_PATH", db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    _migrate(db_path)
    admin = us.create_user("Admin")

    # authenticate the Session token to our admin user
    monkeypatch.setattr(auth, "validate_session", lambda token, idle: admin.id)
    monkeypatch.setattr(auth, "has_role", lambda user, roles: True)
    monkeypatch.setattr(us, "get_by_id", lambda uid: admin)

    # a real agent definition exists in the store
    import fleetent.agent_store as agent_store

    agent_store.create_agent("support", "Help.", ["shell"])

    # controller with a fake spawn so no real process is launched
    proc = _FakeProc()
    monkeypatch.setattr(
        lifecycle_admin_api, "_controller", controller.AgentController(spawn=lambda name: proc)
    )

    app = FastAPI()
    app.include_router(lifecycle_admin_api.router)
    return TestClient(app), tmp_path


_AUTH = {"Authorization": "Session tok"}


def test_start_materializes_and_spawns(client):
    cl, tmp_path = client
    resp = cl.post("/admin/agents/support/start", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["pid"] == 321
    # materialized the home
    assert (tmp_path / "support" / "agent.yaml").exists()
    assert materialize.home_dir("support").joinpath(".env").exists()


def test_status_reflects_running_then_stopped(client):
    cl, _ = client
    cl.post("/admin/agents/support/start", headers=_AUTH)
    assert cl.get("/admin/agents/support/runtime-status", headers=_AUTH).json()["running"] is True

    stop = cl.post("/admin/agents/support/stop", headers=_AUTH)
    assert stop.json()["status"] == "stopped"
    assert cl.get("/admin/agents/support/runtime-status", headers=_AUTH).json()["running"] is False


def test_stop_when_not_started(client):
    cl, _ = client
    resp = cl.post("/admin/agents/support/stop", headers=_AUTH)
    assert resp.json()["status"] == "not-running"


def test_start_unknown_agent_404(client):
    cl, _ = client
    assert cl.post("/admin/agents/ghost/start", headers=_AUTH).status_code == 404


def test_requires_auth(client):
    cl, _ = client
    assert cl.post("/admin/agents/support/start").status_code == 401


def test_router_wired_into_platform_app():
    import fleetent.server as srv

    paths = {getattr(r, "path", None) for r in srv.app.routes}
    assert "/admin/agents/{name}/start" in paths
    assert "/admin/agents/{name}/stop" in paths
