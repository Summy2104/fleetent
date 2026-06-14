"""The platform app is a control plane: boots agent-free, no execution endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations

_OWNER_ROUTE = "/admin/im/" + "connectors"
_OWNER_MANAGER_ATTR = "_connector" + "_manager"


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _server(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import fleetent.server as srv

    return srv


def test_platform_boots_agent_free_no_im(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    start_from_index = AsyncMock()
    monkeypatch.setattr(srv._slack_supervisor, "start_from_index", start_from_index)

    client = TestClient(srv.app)
    assert client.get("/health").status_code == 200

    # Control plane: no IM connector / supervisor started at boot.
    start_from_index.assert_not_called()
    assert not hasattr(srv, _OWNER_MANAGER_ATTR)
    # No agent-use sandbox runtime probed/stashed on the platform.
    assert not hasattr(srv.app.state, "sandbox_mode")


def test_admin_router_removed(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    client = TestClient(srv.app)
    assert client.get(_OWNER_ROUTE).status_code == 404


def test_chat_endpoint_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    client = TestClient(srv.app)
    assert client.post("/chat", json={"message": "hi"}).status_code == 404


def test_webhook_endpoint_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    client = TestClient(srv.app)
    assert client.post("/webhook/some-source", json={}).status_code == 404


def test_ws_route_absent(tmp_path, monkeypatch, isolated_schedule_db):
    srv = _server(tmp_path, monkeypatch)
    paths = {getattr(r, "path", None) for r in srv.app.routes}
    assert "/ws" not in paths
    assert "/chat" not in paths
    assert not any(p and p.startswith("/webhook") for p in paths)
