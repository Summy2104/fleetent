"""Tests for server lifespan wiring: MCP startup, adapter env detection, health."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
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

    # Patch adapter starters to avoid real socket connections during lifespan
    with (
        patch.object(srv, "_start_slack_adapter", new_callable=AsyncMock),
        patch.object(srv, "_start_telegram_adapter", new_callable=AsyncMock),
        TestClient(srv.app) as client,
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["adapters"]["slack"] is True
    assert data["adapters"]["telegram"] is True


async def test_mcp_yaml_loaded_if_exists(tmp_path, monkeypatch):
    """Lifespan calls register_all with servers from config/mcp.yaml."""
    import fleetent.mcp_client as mcp_mod
    import fleetent.server as srv

    mcp_yaml = tmp_path / "mcp.yaml"
    mcp_yaml.write_text(yaml.dump({"servers": [{"id": "test", "url": "http://mcp.example.com"}]}))

    mock_register = AsyncMock(return_value=None)
    monkeypatch.setattr(mcp_mod, "register_all", mock_register)
    monkeypatch.setattr(srv, "_MCP_YAML_PATH", mcp_yaml)
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")

    with TestClient(srv.app) as client:
        client.get("/health")

    mock_register.assert_called_once()
    servers_arg = mock_register.call_args[0][0]
    assert len(servers_arg) == 1
    assert servers_arg[0].id == "test"


async def test_mcp_yaml_missing_skipped_gracefully(tmp_path, monkeypatch):
    """Lifespan skips MCP loading if config/mcp.yaml doesn't exist."""
    import fleetent.mcp_client as mcp_mod
    import fleetent.server as srv

    mock_register = AsyncMock(return_value=None)
    monkeypatch.setattr(mcp_mod, "register_all", mock_register)
    monkeypatch.setattr(srv, "_MCP_YAML_PATH", Path("/nonexistent/mcp.yaml"))
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")

    with TestClient(srv.app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    mock_register.assert_not_called()
