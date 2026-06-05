"""Tests for server lifespan wiring: adapter env detection, health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import fleetent.user_store as us


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    return TestClient(app_module().app)


def app_module():
    import fleetent.server as srv

    return srv


def test_health_includes_adapter_status(tmp_path, monkeypatch):
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


def test_health_adapter_flags_true_when_tokens_set(tmp_path, monkeypatch):
    """Health endpoint shows True for adapters whose env tokens are present."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-fake")

    import fleetent.server as srv

    # _connector_manager still exists on the module; patching its starters is harmless
    # (the control-plane lifespan never starts connectors anyway).
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


def test_lifespan_does_not_crash_when_docker_unavailable(tmp_path, monkeypatch):
    """Platform boots normally and /health is served (control plane has no Docker probe)."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    import fleetent.server as srv

    with TestClient(srv.app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
