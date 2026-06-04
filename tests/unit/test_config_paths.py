"""Config/server path constants derive from the central resolver."""

from pathlib import Path

import pytest

from fleetent import paths
from fleetent import server as srv
from fleetent.config import Settings


def test_config_module_constants_derive_from_paths() -> None:
    import fleetent.config as cfg

    assert cfg.SETTINGS_YAML_PATH == paths.settings_yaml_path()
    assert cfg.MCP_SERVERS_YAML_PATH == paths.config_dir() / "mcp.servers.yaml"


def test_server_yaml_constants_derive_from_paths() -> None:
    assert srv._MCP_YAML_PATH == paths.config_dir() / "mcp.yaml"
    assert srv._WEBHOOK_YAML_PATH == paths.config_dir() / "webhooks.yaml"


def test_settings_default_paths_follow_fleetent_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setattr("fleetent.config.SETTINGS_YAML_PATH", tmp_path / "missing.yaml")

    s = Settings(anthropic_api_key="test-key")

    assert s.database_url == f"sqlite:///{tmp_path / 'data' / 'fleetent.db'}"
    assert s.observability.logging.directory == str(tmp_path / "data" / "logs")
    assert s.diagnostics.export_dir == str(tmp_path / "data" / "diagnostics")
