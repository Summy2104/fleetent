import pytest
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.user_store as us
from fleetent.server import app
from tests.integration.test_migrations import apply_migrations


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "adapters" in data


def test_kb_router_mounted():
    from fleetent.server import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/admin/kb" in paths  # knowledge-base management router is mounted


# ── cron scheduler lifespan ───────────────────────────────────────────────────


def test_lifespan_loads_plugins(tmp_path, monkeypatch):
    """Startup invokes plugin_loader.load_plugins() once, alongside scan_skills."""
    from unittest.mock import patch

    import fleetent.server as srv

    with patch("fleetent.server.load_plugins") as mock_load, TestClient(srv.app):
        pass
    mock_load.assert_called_once()


def test_lifespan_starts_platform_maintenance_scheduler(tmp_path, monkeypatch):
    """agent-owned-scheduled-tasks: platform lifespan runs a bare maintenance scheduler
    (playground retention only) — it no longer loads/fires user scheduled tasks."""
    from unittest.mock import MagicMock, patch

    from starlette.testclient import TestClient

    import fleetent.server as srv

    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setattr(us, "DB_PATH", db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    instance = MagicMock()
    instance.running = True
    with (
        patch("fleetent.server.AsyncIOScheduler", return_value=instance) as mock_cls,
        TestClient(srv.app),
    ):
        pass  # lifespan runs on enter/exit

    mock_cls.assert_called_once()
    instance.start.assert_called_once()
    instance.shutdown.assert_called_once()
    job_ids = {c.kwargs.get("id") for c in instance.add_job.call_args_list}
    assert "playground_retention" in job_ids


def test_lifespan_does_not_load_scheduled_tasks(tmp_path, monkeypatch):
    """The platform server must not touch schedule_store (user tasks are agent-owned)."""
    from unittest.mock import patch

    from starlette.testclient import TestClient

    import fleetent.schedule_store as schedule_store
    import fleetent.server as srv

    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setattr(us, "DB_PATH", db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    with patch.object(schedule_store, "list_tasks") as list_mock, TestClient(srv.app):
        pass

    list_mock.assert_not_called()


# --- agent_store seam wiring (clone/apply persist in production) --------------


def _agent_admin_env(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # platform-agent-lifecycle: create/update now materializes the agent home; isolate
    # FLEETENT_HOME to tmp so the seam never writes to the real data dir.
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setattr(us, "DB_PATH", db_path)
    monkeypatch.setattr(audit, "DB_PATH", db_path)
    return db_path


def _admin_session() -> str:
    u = us.create_user("admin-user")
    us.set_role(u.id, "admin")
    return auth.create_session(u.id)


def test_clone_persists_via_wired_seam(tmp_path, monkeypatch, isolated_schedule_db):
    _agent_admin_env(tmp_path, monkeypatch)
    agent_store.create_agent("ops", "Ops prompt", ["read_*"])
    token = _admin_session()
    client = TestClient(app)
    r = client.post(
        "/admin/agents/ops/clone",
        headers={"Authorization": f"Session {token}"},
        json={"new_name": "ops-copy"},
    )
    assert r.status_code == 200
    copy = agent_store.get_by_name("ops-copy")
    assert copy is not None and copy.system_prompt == "Ops prompt"


def test_apply_persists_via_wired_seam(tmp_path, monkeypatch, isolated_schedule_db):
    _agent_admin_env(tmp_path, monkeypatch)
    token = _admin_session()
    client = TestClient(app)
    r = client.post(
        "/admin/agents/apply",
        headers={"Authorization": f"Session {token}"},
        json={"name": "fresh", "system_prompt": "Fresh.", "allowed_tools": ["shell"]},
    )
    assert r.status_code == 200
    found = agent_store.get_by_name("fresh")
    assert found is not None and found.system_prompt == "Fresh."


def test_create_persists_version_config_via_wired_seam(tmp_path, monkeypatch, isolated_schedule_db):
    _agent_admin_env(tmp_path, monkeypatch)
    token = _admin_session()
    client = TestClient(app)
    r = client.post(
        "/admin/agents",
        headers={"Authorization": f"Session {token}"},
        json={
            "name": "cfg",
            "template_id": "ops",
            "system_prompt": "hi",
            "allowed_tools": ["shell"],
            "skills_dir": "/s",
            "mcp_server_ids": ["github"],
            "model_overrides": {"model": "x"},
            "memory_namespace": "team",
        },
    )
    assert r.status_code == 201
    a = agent_store.get_by_name("cfg")
    assert a.skills_dir == "/s"
    assert a.mcp_server_ids == ["github"]
    assert a.model_overrides == {"model": "x"}
    assert a.memory_namespace == "team"
    # platform-agent-lifecycle: create materialized the runnable home
    assert (tmp_path / "agents" / "cfg" / "agent.yaml").exists()


def test_update_overrides_only_provided_via_wired_seam(tmp_path, monkeypatch, isolated_schedule_db):
    _agent_admin_env(tmp_path, monkeypatch)
    agent_store.create_agent("cfg", "v1", ["shell"], skills_dir="/s")
    token = _admin_session()
    client = TestClient(app)
    r = client.patch(
        "/admin/agents/cfg",
        headers={"Authorization": f"Session {token}"},
        json={"memory_namespace": "team"},
    )
    assert r.status_code == 200
    a = agent_store.get_by_name("cfg")
    assert a.memory_namespace == "team"
    assert a.skills_dir == "/s"  # inherited
