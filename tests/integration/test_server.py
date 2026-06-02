import pytest
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


@pytest.fixture(autouse=True)
def isolate_runtime_config_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch, isolated_schedule_db):
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


def test_chat_valid_token_streams(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    received_user_ids: list[str] = []

    async def fake_stream(msg: str, user_id: str):  # type: ignore[misc]
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


def test_chat_stream_exception_yields_error_event(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.server as srv
    import fleetent.user_store as us2

    _migrated_db(tmp_path, monkeypatch)

    async def error_stream(msg: str, user_id: str):  # type: ignore[misc]
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


def test_chat_uses_channel_agent_when_headers_provided(tmp_path, monkeypatch, isolated_schedule_db):
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
        agent_name: str | None = None,
        snapshot=None,
    ):  # type: ignore[misc]
        captured["system_prompt"] = system_prompt
        captured["agent_name"] = agent_name
        captured["snapshot"] = snapshot
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
    assert captured.get("agent_name") == "channel-bot"
    assert captured["snapshot"] is not None
    assert captured["snapshot"].allowed_tools == ["shell"]
    assert captured["snapshot"].version_id == channel_agent.active_version_id


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


# ── cron scheduler lifespan ───────────────────────────────────────────────────


def test_lifespan_starts_and_stops_cron_scheduler(tmp_path, monkeypatch, isolated_schedule_db):
    from unittest.mock import AsyncMock, patch

    from starlette.testclient import TestClient

    import fleetent.server as srv

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
