"""Tests for server lifespan wiring: MCP startup, adapter env detection, health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import fleetent.config as cfg
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


async def test_mcp_servers_loaded_from_dedicated_file(tmp_path, monkeypatch, isolated_schedule_db):
    """Lifespan calls register_all with servers from config/mcp.servers.yaml."""
    import fleetent.mcp_client as mcp_mod
    import fleetent.server as srv

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings_yaml = config_dir / "settings.yaml"
    settings_yaml.write_text("mcp:\n  enabled: true\n")
    (config_dir / "mcp.servers.yaml").write_text(
        "\n".join(
            [
                "servers:",
                "  - id: test",
                "    url: http://mcp.example.com",
            ]
        )
    )

    mock_register = AsyncMock(return_value=None)
    monkeypatch.setattr(mcp_mod, "register_all", mock_register)
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    with TestClient(srv.app) as client:
        client.get("/health")

    mock_register.assert_called_once()
    servers_arg = mock_register.call_args[0][0]
    assert len(servers_arg) == 1
    assert servers_arg[0].id == "test"


async def test_missing_mcp_servers_file_skips_registration(
    tmp_path, monkeypatch, isolated_schedule_db
):
    """Lifespan skips MCP loading if config/mcp.servers.yaml is missing."""
    import fleetent.mcp_client as mcp_mod
    import fleetent.server as srv

    mock_register = AsyncMock(return_value=None)
    monkeypatch.setattr(mcp_mod, "register_all", mock_register)
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", tmp_path / "missing-settings.yaml")
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    with TestClient(srv.app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    mock_register.assert_not_called()


async def test_mcp_disabled_skips_dedicated_file(tmp_path, monkeypatch, isolated_schedule_db):
    """Lifespan does not read config/mcp.servers.yaml when mcp.enabled is false."""
    import fleetent.mcp_client as mcp_mod
    import fleetent.server as srv

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings_yaml = config_dir / "settings.yaml"
    settings_yaml.write_text("mcp:\n  enabled: false\n")
    (config_dir / "mcp.servers.yaml").write_text("servers: [")

    mock_register = AsyncMock(return_value=None)
    monkeypatch.setattr(mcp_mod, "register_all", mock_register)
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    with TestClient(srv.app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    mock_register.assert_not_called()


async def test_legacy_mcp_yaml_fails_fast(tmp_path, monkeypatch, isolated_schedule_db):
    """Startup rejects config/mcp.yaml instead of falling back to legacy loading."""
    import fleetent.server as srv

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp.yaml").write_text("servers: []\n")
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", config_dir / "settings.yaml")
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="config/mcp.servers.yaml"), TestClient(srv.app):
        pass
