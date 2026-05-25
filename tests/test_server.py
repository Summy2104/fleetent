import pytest
from fastapi.testclient import TestClient

import mini_agent.user_store as us
from mini_agent.server import app


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
    import mini_agent.server as srv
    import mini_agent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")

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


def test_require_auth_non_bearer_scheme(client):
    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Token abc123"},
    )
    assert resp.status_code == 401


def test_chat_stream_exception_yields_error_event(tmp_path, monkeypatch):
    import mini_agent.server as srv
    import mini_agent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")

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


def test_chat_uses_channel_agent_when_headers_provided(tmp_path, monkeypatch):
    """/chat with x-platform + x-channel-id uses the channel-bound agent."""
    import mini_agent.server as srv
    import mini_agent.user_store as us2
    import mini_agent.agent_store as ag

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ag, "DB_PATH", tmp_path / "users.db")

    captured: dict = {}

    async def fake_stream(msg: str, user_id: str, system_prompt: str | None = None, allowed_tools=None, agent_name: str | None = None):  # type: ignore[misc]
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


# ── cron scheduler lifespan ───────────────────────────────────────────────────

def test_lifespan_starts_and_stops_cron_scheduler(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch
    from starlette.testclient import TestClient
    import mini_agent.server as srv

    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH", tmp_path / "webhooks.yaml")

    start_mock = AsyncMock()
    shutdown_mock = AsyncMock()

    with patch("mini_agent.server.CronScheduler") as mock_cls:
        instance = mock_cls.return_value
        instance.start = start_mock
        instance.shutdown = shutdown_mock

        with TestClient(srv.app):
            pass  # lifespan runs on enter/exit

    start_mock.assert_called_once()
    shutdown_mock.assert_called_once()
