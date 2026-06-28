import base64

import pytest
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.user_store as us
from fleetent.agent_config import default_models
from fleetent.platform.agent_lifecycle import materialize
from fleetent.server import app
from tests.integration.test_migrations import apply_migrations


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
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


def test_node_router_mounted():
    from fleetent.server import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/nodes/{node_id}/desired-state" in paths
    assert "/nodes/{node_id}/status" in paths


def test_lifespan_initializes_skill_pool_as_git_repo(tmp_path, monkeypatch):
    """Platform boot must make the shared skill pool a git repo.

    Regression: a non-git pool made backflow accept/fork raise FileNotFoundError
    (.git/fleetent.lock) and return 500. The pool-is-a-git-repo invariant must be
    established by the platform at startup, not left to a manual init.
    """
    from fleetent.platform.skill_management.pool_git import _is_git_repo

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mgmt.db'}")
    apply_migrations(tmp_path / "mgmt.db")
    pool = tmp_path / "skills"
    (pool / "demo").mkdir(parents=True)
    (pool / "demo" / "SKILL.md").write_text("---\nname: demo\n---\nbody\n", encoding="utf-8")
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool))

    assert not _is_git_repo(pool)  # before boot: a plain directory
    with TestClient(app):  # trigger lifespan startup
        pass
    assert _is_git_repo(pool)  # after boot: platform has git-initialized the pool


def test_backflow_router_mounted(client):
    from fleetent.server import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/admin/skills/backflow" in paths
    assert "/admin/skills/backflow/{proposal_id}/diff" in paths
    assert "/admin/skills/backflow/{proposal_id}/accept" in paths
    assert "/admin/skills/backflow/{proposal_id}/reject" in paths
    assert "/admin/skills/backflow/{proposal_id}/fork" in paths
    # Mounted and reachable: unauthenticated list returns 401 (auth), not 404 (no route).
    assert client.get("/admin/skills/backflow").status_code == 401


def test_no_shared_memory_admin_router(client) -> None:
    import fleetent.server as srv

    paths = {getattr(r, "path", None) for r in srv.app.routes}
    assert "/admin/memory/shared" not in paths
    assert not hasattr(srv, "shared_memory_admin_api")
    assert client.get("/admin/memory/shared?scope_type=team&scope_id=eng").status_code == 404


def test_observability_admin_routes_not_mounted() -> None:
    import fleetent.server as srv

    paths = {getattr(r, "path", None) for r in srv.app.routes}
    assert "/admin/observability/traces" not in paths
    assert "/admin/observability/usage" not in paths
    assert "/admin/observability/performance" not in paths


# ── cron scheduler lifespan ───────────────────────────────────────────────────


def test_lifespan_loads_plugins(tmp_path, monkeypatch):
    """Startup invokes plugin_loader.load_plugins() once, alongside scan_skills."""
    from unittest.mock import patch

    import fleetent.server as srv

    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    with patch("fleetent.server.load_plugins") as mock_load, TestClient(srv.app):
        pass
    mock_load.assert_called_once()


def test_lifespan_has_no_platform_maintenance_scheduler(tmp_path, monkeypatch):
    """drop-platform-playground: platform lifespan no longer starts a maintenance scheduler."""

    from unittest.mock import AsyncMock

    from starlette.testclient import TestClient

    import fleetent.server as srv

    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )

    assert not hasattr(srv, "AsyncIOScheduler")
    with TestClient(srv.app):
        pass  # lifespan runs on enter/exit


def test_lifespan_does_not_load_scheduled_tasks(tmp_path, monkeypatch):
    """The platform server must not touch schedule_store (user tasks are agent-owned)."""
    from unittest.mock import patch

    from starlette.testclient import TestClient

    import fleetent.schedule_store as schedule_store
    import fleetent.server as srv

    db = tmp_path / "users.db"
    apply_migrations(db)
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
    return db_path


def _admin_session() -> str:
    u, _ = us.create_user("admin-user")
    us.set_role(u.id, "admin")
    return auth.create_session(u.id)


def _model_overrides_payload() -> dict[str, object]:
    return {
        "routes": {
            "default": [
                {
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5-20251001",
                    "base_url": "https://api.anthropic.com/v1/",
                    "api_key_env": "FLEETENT_MODEL_PRIMARY_API_KEY",
                    "protocol": "openai_chat",
                    "max_tokens": 1024,
                    "params": {"temperature": 0.1},
                }
            ]
        }
    }


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
    assert not (tmp_path / "tenants" / "default" / "agents" / "ops-copy").exists()


def test_apply_endpoint_not_wired_in_server(tmp_path, monkeypatch, isolated_schedule_db):
    _agent_admin_env(tmp_path, monkeypatch)
    token = _admin_session()
    client = TestClient(app)
    r = client.post(
        "/admin/agents/apply",
        headers={"Authorization": f"Session {token}"},
        json={"name": "fresh", "system_prompt": "Fresh.", "allowed_tools": ["shell"]},
    )
    assert r.status_code == 405


def test_apply_endpoint_not_wired_in_server_even_with_model_overrides(
    tmp_path, monkeypatch, isolated_schedule_db
):
    _agent_admin_env(tmp_path, monkeypatch)
    token = _admin_session()
    client = TestClient(app)
    model_overrides = _model_overrides_payload()

    r = client.post(
        "/admin/agents/apply",
        headers={"Authorization": f"Session {token}"},
        json={
            "name": "fresh-model",
            "system_prompt": "Fresh.",
            "allowed_tools": ["shell"],
            "model_overrides": model_overrides,
        },
    )

    assert r.status_code == 405


def test_apply_endpoint_not_wired_for_existing_and_fresh_agents(
    tmp_path, monkeypatch, isolated_schedule_db
):
    _agent_admin_env(tmp_path, monkeypatch)
    seed_overrides = _model_overrides_payload()
    agent_store.create_agent("existing-model", "Before.", ["shell"], model_overrides=seed_overrides)
    token = _admin_session()
    client = TestClient(app)

    update = client.post(
        "/admin/agents/apply",
        headers={"Authorization": f"Session {token}"},
        json={
            "name": "existing-model",
            "system_prompt": "After.",
            "allowed_tools": ["shell", "read_file"],
        },
    )

    assert update.status_code == 405

    fresh = client.post(
        "/admin/agents/apply",
        headers={"Authorization": f"Session {token}"},
        json={
            "name": "fresh-null-model",
            "system_prompt": "Fresh.",
            "allowed_tools": ["shell"],
            "model_overrides": None,
        },
    )

    assert fresh.status_code == 405


def test_update_materializes_configured_model_overrides_via_console_write_path(
    tmp_path, monkeypatch, isolated_schedule_db
):
    _agent_admin_env(tmp_path, monkeypatch)
    token = _admin_session()
    client = TestClient(app)
    created = client.post(
        "/admin/agents",
        headers={"Authorization": f"Session {token}"},
        json={"name": "materialized-model", "system_prompt": "Fresh.", "allowed_tools": ["shell"]},
    )
    assert created.status_code == 201

    response = client.patch(
        "/admin/agents/materialized-model",
        headers={"Authorization": f"Session {token}"},
        json={
            "system_prompt": "Fresh.",
            "allowed_tools": ["shell"],
            "model_overrides": _model_overrides_payload(),
        },
    )

    assert response.status_code == 200
    exported = materialize.agent_file_from_store(agent_store.get_by_name("materialized-model"))
    assert exported.models != default_models()
    assert exported.models.routes["default"][0].target == "anthropic"
    target = {item.id: item for item in exported.models.targets}["anthropic"]
    assert target.provider == "anthropic"
    assert target.model == "claude-haiku-4-5-20251001"
    assert target.base_url == "https://api.anthropic.com/v1/"
    assert target.api_key_env == "FLEETENT_MODEL_PRIMARY_API_KEY"


def test_update_is_idempotent_for_model_overrides_and_preserves_bindings(
    tmp_path, monkeypatch, isolated_schedule_db
):
    _agent_admin_env(tmp_path, monkeypatch)
    seed_overrides = _model_overrides_payload()
    agent = agent_store.create_agent(
        "stable-model", "Before.", ["shell"], model_overrides=seed_overrides
    )
    agent_store.assign_user("user-1", agent.id)
    token = _admin_session()
    client = TestClient(app)
    patch_payload = {
        "system_prompt": "After.",
        "allowed_tools": ["shell", "read_file"],
        "model_overrides": seed_overrides,
    }
    first = client.patch(
        "/admin/agents/stable-model",
        headers={"Authorization": f"Session {token}"},
        json=patch_payload,
    )
    second = client.patch(
        "/admin/agents/stable-model",
        headers={"Authorization": f"Session {token}"},
        json=patch_payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    found = agent_store.get_by_name("stable-model")
    assert found is not None
    assert found.system_prompt == "After."
    assert found.allowed_tools == ["shell", "read_file"]
    assert found.model_overrides == seed_overrides
    assert agent_store.list_users_for_agent(found.id) == ["user-1"]
    assert found.version == 3


def test_update_model_overrides_keep_api_key_env_name_without_secret_value(
    tmp_path, monkeypatch, isolated_schedule_db
):
    _agent_admin_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
    )
    token = _admin_session()
    client = TestClient(app)
    model_overrides = _model_overrides_payload()
    created = client.post(
        "/admin/agents",
        headers={"Authorization": f"Session {token}"},
        json={"name": "secret-safe-model", "system_prompt": "Fresh.", "allowed_tools": ["shell"]},
    )
    assert created.status_code == 201

    applied = client.patch(
        "/admin/agents/secret-safe-model",
        headers={"Authorization": f"Session {token}"},
        json={
            "system_prompt": "Fresh.",
            "allowed_tools": ["shell"],
            "model_overrides": model_overrides,
        },
    )
    secret = client.put(
        "/admin/agents/secret-safe-model/secrets/FLEETENT_MODEL_PRIMARY_API_KEY",
        headers={"Authorization": f"Session {token}"},
        json={"value": "sk-live-secret"},
    )

    assert applied.status_code == 200
    assert secret.status_code == 200
    found = agent_store.get_by_name("secret-safe-model")
    assert found is not None
    assert found.model_overrides["routes"] == model_overrides["routes"]
    assert (
        found.model_overrides["routes"]["default"][0]["api_key_env"]
        == "FLEETENT_MODEL_PRIMARY_API_KEY"
    )
    assert "sk-live-secret" not in str(found.model_overrides)


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
    assert not (tmp_path / "tenants" / "default" / "agents" / "cfg").exists()


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
    assert not (tmp_path / "tenants" / "default" / "agents" / "cfg").exists()
