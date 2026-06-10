"""Tests for server lifespan wiring: MCP startup, adapter env detection, health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import fleetent.user_store as us
from tests.integration._migration_template import apply_migrations


@pytest.fixture(autouse=True)
def isolate_runtime_config_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch, isolated_schedule_db):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
    return TestClient(app_module().app)


def app_module():
    import fleetent.server as srv

    return srv


def test_health_includes_adapter_status(tmp_path, monkeypatch, isolated_schedule_db):
    """Health endpoint returns adapter presence flags; both False when no tokens."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
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


def test_health_adapter_flags_true_when_connectors_present(
    tmp_path, monkeypatch, isolated_schedule_db
):
    """Health reflects per-agent Slack + owner Telegram connector presence."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")

    import fleetent.server as srv

    # Slack is per-agent (agent.yaml connectors.slack); Telegram is owner-level.
    monkeypatch.setattr(srv, "_slack_adapter_configured", lambda: True)
    monkeypatch.setattr(srv, "_telegram_adapter_configured", lambda: True)

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


def test_admin_im_router_mounted(tmp_path, monkeypatch, isolated_schedule_db):
    """`/admin/im/connectors` is mounted: unauthenticated request gets 401, not 404."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)

    import fleetent.server as srv

    with (
        patch.object(srv._connector_manager, "start_all_enabled", new_callable=AsyncMock),
        patch.object(srv._connector_manager, "stop", new_callable=AsyncMock),
        TestClient(srv.app) as client,
    ):
        resp = client.get("/admin/im/connectors")

    assert resp.status_code == 401
