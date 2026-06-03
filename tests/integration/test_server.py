from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import fleetent.user_store as us
from fleetent.server import app
from tests.integration.test_migrations import apply_migrations


def _migrated_db(tmp_path, monkeypatch):
    """Point user_store (DB_PATH) and agent_store (DATABASE_URL) at one migrated DB."""
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(us, "DB_PATH", db_path)
    return db_path


def _apply_migrations(db_path) -> None:
    """Provision the unified-runtime schema (agents etc.) for a tmp_path db.

    agent_store moved off raw DB_PATH onto the unified db runtime, so server tests
    that touch agents must apply alembic migrations rather than monkeypatch
    agent_store.DB_PATH (which no longer exists). user_store still uses DB_PATH.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    return TestClient(app)


@pytest.fixture()
def auth_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    user = us.create_user("Tester")
    return {"Authorization": f"Bearer {user.api_key}"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "adapters" in data


def test_chat_no_auth(client):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422  # missing header


def test_chat_invalid_token(client):
    resp = client.post(
        "/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer ma-invalid"},
    )
    assert resp.status_code == 401


def test_chat_valid_token_streams(tmp_path, monkeypatch):
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    received_user_ids: list[str] = []

    async def fake_stream(msg: str, user_id: str, **kwargs):  # type: ignore[misc]
        received_user_ids.append(user_id)
        yield {"type": "text_delta", "content": "hi"}
        yield {"type": "done", "content": "hi"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("StreamTester")
    with TestClient(app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "done" in resp.text
    assert received_user_ids == [user.id]  # user_id flows from auth to run_stream


def test_chat_over_quota_returns_429(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.governance.quota as quota
    import fleetent.server as srv
    import fleetent.user_store as us2

    db_path = _migrated_db(tmp_path, monkeypatch)
    monkeypatch.setattr(quota, "DB_PATH", db_path)

    events: list[str] = []
    monkeypatch.setattr(srv, "_emit_over_quota_event", lambda uid: events.append(uid))

    user = us2.create_user("QuotaUser")
    quota.set_quota(f"user:{user.id}", call_limit=0)  # already exhausted

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 429
    assert "quota" in resp.json()["detail"].lower()
    assert events == [user.id]  # over-quota event emitted


def test_kb_router_mounted():
    from fleetent.server import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/admin/kb" in paths  # knowledge-base management router is mounted


def test_require_auth_non_bearer_scheme(client):
    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Token abc123"},
    )
    assert resp.status_code == 401


def test_chat_stream_exception_yields_error_event(tmp_path, monkeypatch):
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    async def error_stream(msg: str, user_id: str, **kwargs):  # type: ignore[misc]
        raise RuntimeError("boom")
        yield  # makes this an async generator

    monkeypatch.setattr(srv, "run_stream", error_stream)
    user = us2.create_user("ErrUser")
    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert "boom" in resp.text


def test_chat_uses_channel_agent_when_headers_provided(tmp_path, monkeypatch):
    """/chat with x-platform + x-channel-id uses the channel-bound agent."""
    import fleetent.agent_store as ag
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    captured: dict = {}

    async def fake_stream(
        msg: str,
        user_id: str,
        system_prompt: str | None = None,
        allowed_tools=None,
        agent_name: str | None = None,
        **kwargs,
    ):  # type: ignore[misc]
        captured["system_prompt"] = system_prompt
        captured["allowed_tools"] = allowed_tools
        captured["agent_name"] = agent_name
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("ChannelTester")
    channel_agent = ag.create_agent("channel-bot", "Channel system.", ["shell"])
    ag.assign_channel("slack", "C-TEST", channel_agent.id)

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hello"},
            headers={
                "Authorization": f"Bearer {user.api_key}",
                "x-platform": "slack",
                "x-channel-id": "C-TEST",
            },
        )
    assert resp.status_code == 200
    assert captured.get("system_prompt") == "Channel system."
    assert captured.get("allowed_tools") == ["shell"]
    assert captured.get("agent_name") == "channel-bot"


def test_chat_rejects_disabled_agent(tmp_path, monkeypatch, isolated_schedule_db):
    """/chat must refuse a disabled agent and never enter the agent loop (task 8)."""
    import fleetent.agent_store as ag
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    entered = []

    async def fake_stream(msg, **kwargs):  # type: ignore[misc]
        entered.append(msg)
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)
    monkeypatch.setattr(srv, "agent_routing_status", lambda name: "disabled")

    user = us2.create_user("DisabledChan")
    agent = ag.create_agent("paused-bot", "x", ["shell"])
    ag.assign_channel("slack", "C-OFF", agent.id)

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={
                "Authorization": f"Bearer {user.api_key}",
                "x-platform": "slack",
                "x-channel-id": "C-OFF",
            },
        )
    assert resp.status_code == 403
    assert "停用" in resp.json()["detail"]
    assert entered == []  # never reached the agent loop


def test_chat_rejects_archived_agent(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.agent_store as ag
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "agent_routing_status", lambda name: "archived")

    user = us2.create_user("ArchChan")
    agent = ag.create_agent("gone-bot", "x", ["shell"])
    ag.assign_channel("slack", "C-ARC", agent.id)

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={
                "Authorization": f"Bearer {user.api_key}",
                "x-platform": "slack",
                "x-channel-id": "C-ARC",
            },
        )
    assert resp.status_code == 403


def test_chat_merges_agent_plugins_into_allowed_tools(tmp_path, monkeypatch):
    """An agent's plugins expand to `{name}__*` patterns merged into allowed_tools."""
    import fleetent.agent_store as ag
    import fleetent.server as srv
    import fleetent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    _apply_migrations(tmp_path / "users.db")

    captured: dict = {}

    async def fake_stream(
        msg: str,
        user_id: str,
        system_prompt: str | None = None,
        allowed_tools=None,
        agent_name: str | None = None,
        **kwargs,
    ):  # type: ignore[misc]
        captured["allowed_tools"] = allowed_tools
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("PluginTester")
    agent = ag.create_agent("plugin-bot", "Sys.", ["shell"], plugins=["crm_tools", "billing"])
    ag.assign_channel("slack", "C-PLUG", agent.id)

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={
                "Authorization": f"Bearer {user.api_key}",
                "x-platform": "slack",
                "x-channel-id": "C-PLUG",
            },
        )
    assert resp.status_code == 200
    allowed = captured.get("allowed_tools")
    assert allowed is not None
    assert "shell" in allowed
    assert "crm_tools__*" in allowed
    assert "billing__*" in allowed


# ── cron scheduler lifespan ───────────────────────────────────────────────────


def test_lifespan_loads_plugins(tmp_path, monkeypatch):
    """Startup invokes plugin_loader.load_plugins() once, alongside scan_skills."""
    from unittest.mock import patch

    import fleetent.server as srv

    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH", tmp_path / "webhooks.yaml")
    monkeypatch.setattr(srv, "_MCP_YAML_PATH", tmp_path / "mcp.yaml")

    with patch("fleetent.server.load_plugins") as mock_load, TestClient(srv.app):
        pass
    mock_load.assert_called_once()


def test_lifespan_starts_and_stops_cron_scheduler(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from starlette.testclient import TestClient

    import fleetent.server as srv

    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH", tmp_path / "webhooks.yaml")

    start_mock = AsyncMock()
    shutdown_mock = AsyncMock()

    with patch("fleetent.server.CronScheduler") as mock_cls:
        instance = mock_cls.return_value
        instance.start = start_mock
        instance.shutdown = shutdown_mock

        with TestClient(srv.app):
            pass  # lifespan runs on enter/exit

    start_mock.assert_called_once()
    shutdown_mock.assert_called_once()


def test_chat_passes_sandbox_mode_to_run_stream(tmp_path, monkeypatch):
    """The effective sandbox mode resolved at startup flows into run_stream."""
    import fleetent.integrations.sandbox.client as sc
    import fleetent.integrations.sandbox.enablement as se
    import fleetent.server as srv
    import fleetent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    _apply_migrations(tmp_path / "users.db")
    # server imports load_sandbox_mode by name; patch the name in server's namespace.
    monkeypatch.setattr(srv, "load_sandbox_mode", lambda: se.Mode.SELECTIVE)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(sc.SandboxClient, "docker_available", AsyncMock(return_value=True))

    captured: dict = {}

    async def fake_stream(msg, user_id, **kwargs):  # type: ignore[misc]
        captured.update(kwargs)
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("SbTester")
    with TestClient(app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 200
    assert captured.get("sandbox_mode") == se.Mode.SELECTIVE


def test_chat_passes_agent_allowed_skills_to_run_stream(tmp_path, monkeypatch):
    """An agent's allowed_skills flow into run_stream for catalog narrowing."""
    import fleetent.agent_store as ag
    import fleetent.server as srv
    import fleetent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    _apply_migrations(tmp_path / "users.db")

    captured: dict = {}

    async def fake_stream(msg: str, user_id: str, **kwargs):  # type: ignore[misc]
        captured["allowed_skills"] = kwargs.get("allowed_skills")
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("SkillScopeTester")
    agent = ag.create_agent("skill-bot", "Sys.", ["shell"], allowed_skills=["weather"])
    ag.assign_channel("slack", "C-SKILL", agent.id)

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={
                "Authorization": f"Bearer {user.api_key}",
                "x-platform": "slack",
                "x-channel-id": "C-SKILL",
            },
        )
    assert resp.status_code == 200
    assert captured.get("allowed_skills") == ["weather"]


def test_chat_no_agent_passes_no_allowed_skills(tmp_path, monkeypatch):
    """With no bound agent, run_stream receives no allowed_skills (no narrowing)."""
    import fleetent.server as srv
    import fleetent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    _apply_migrations(tmp_path / "users.db")

    captured: dict = {}

    async def fake_stream(msg: str, user_id: str, **kwargs):  # type: ignore[misc]
        captured["has_allowed_skills"] = "allowed_skills" in kwargs
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("NoAgentSkillTester")

    with TestClient(srv.app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 200
    assert captured.get("has_allowed_skills") is False


def test_lifespan_registers_monitoring_collection_job(tmp_path, monkeypatch, isolated_schedule_db):
    """server lifespan wires a periodic monitoring collect/evaluate job (task 9.1)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from starlette.testclient import TestClient

    import fleetent.server as srv

    with patch("fleetent.server.CronScheduler") as mock_cls:
        instance = mock_cls.return_value
        instance.start = AsyncMock()
        instance.shutdown = AsyncMock()
        instance.add_interval_job = MagicMock()

        with TestClient(srv.app):
            pass

    job_ids = {
        c.kwargs.get("job_id", (c.args[2] if len(c.args) > 2 else None))
        for c in instance.add_interval_job.call_args_list
    }
    assert "monitoring_collect" in job_ids
