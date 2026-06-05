"""The platform app is a control plane: boots agent-free, no execution endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import fleetent.user_store as us


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _server(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import fleetent.server as srv

    return srv


def test_platform_boots_agent_free_no_im(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    start_all = AsyncMock()
    start_from_index = AsyncMock()
    monkeypatch.setattr(srv._connector_manager, "start_all_enabled", start_all)
    monkeypatch.setattr(srv._slack_supervisor, "start_from_index", start_from_index)

    with TestClient(srv.app) as client:
        assert client.get("/health").status_code == 200

    # Control plane: no IM connector / supervisor started at boot.
    start_all.assert_not_called()
    start_from_index.assert_not_called()
    # No agent-use sandbox runtime probed/stashed on the platform.
    assert not hasattr(srv.app.state, "sandbox_mode")


def test_admin_router_still_mounted(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    with TestClient(srv.app) as client:
        # mounted but unauthenticated → 401 (not 404)
        assert client.get("/admin/im/connectors").status_code == 401


def test_chat_endpoint_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    with TestClient(srv.app) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 404


def test_webhook_endpoint_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    with TestClient(srv.app) as client:
        assert client.post("/webhook/some-source", json={}).status_code == 404


def test_ws_route_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    paths = {getattr(r, "path", None) for r in srv.app.routes}
    assert "/ws" not in paths
    assert "/chat" not in paths
    assert not any(p and p.startswith("/webhook") for p in paths)
