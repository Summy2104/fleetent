"""Tests for server lifespan wiring: MCP startup, adapter env detection, health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import fleetent.user_store as us


@pytest.fixture(autouse=True)
def isolate_runtime_config_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch, isolated_schedule_db):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    return TestClient(app_module().app)


def app_module():
    import fleetent.server as srv

    return srv


def test_health_includes_adapter_status(tmp_path, monkeypatch, isolated_schedule_db):
    """Health endpoint returns adapter presence flags; both False when no tokens."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here — prevents Settings from loading tokens

    import fleetent.server as srv

    with TestClient(srv.app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["adapters"]["slack"] is False
    assert data["adapters"]["telegram"] is False


def test_health_adapter_flags_true_when_tokens_set(tmp_path, monkeypatch, isolated_schedule_db):
    """Health endpoint shows True for adapters whose env tokens are present."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-fake")

    import fleetent.server as srv

    # Manager start is mocked so lifespan never opens real sockets.
    with (
        patch.object(srv._connector_manager, "start_all_enabled", new_callable=AsyncMock),
        patch.object(srv._connector_manager, "stop", new_callable=AsyncMock),
        TestClient(srv.app) as client,
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["adapters"]["slack"] is True
    assert data["adapters"]["telegram"] is True


def test_lifespan_starts_connectors_via_manager(tmp_path, monkeypatch, isolated_schedule_db):
    """Lifespan drives IM connectors through manager.start_all_enabled, not hardcoded adapters."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-fake")
    monkeypatch.chdir(tmp_path)

    import fleetent.server as srv

    start_all = AsyncMock(return_value=None)
    monkeypatch.setattr(srv._connector_manager, "start_all_enabled", start_all)
    monkeypatch.setattr(srv._connector_manager, "stop", AsyncMock(return_value=None))

    with TestClient(srv.app) as client:
        client.get("/health")

    start_all.assert_called_once()
    # Hardcoded per-adapter starters are gone; manager owns lifecycle now.
    assert not hasattr(srv, "_start_slack_adapter")
    assert not hasattr(srv, "_start_telegram_adapter")


def test_admin_im_router_mounted(tmp_path, monkeypatch, isolated_schedule_db):
    """`/admin/im/connectors` is mounted: unauthenticated request gets 401, not 404."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)

    import fleetent.server as srv

    with (
        patch.object(srv._connector_manager, "start_all_enabled", new_callable=AsyncMock),
        patch.object(srv._connector_manager, "stop", new_callable=AsyncMock),
        TestClient(srv.app) as client,
    ):
        resp = client.get("/admin/im/connectors")

    assert resp.status_code == 401
