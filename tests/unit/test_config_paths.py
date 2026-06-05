"""Config/server path constants derive from the central resolver."""

from pathlib import Path

import pytest

from fleetent import paths
from fleetent.config import Settings


def test_config_module_constants_derive_from_paths(monkeypatch) -> None:
    # Constants are frozen at import (repo-local); match that resolution here.
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    import fleetent.config as cfg

    assert paths.settings_yaml_path() == cfg.SETTINGS_YAML_PATH
    assert paths.config_dir() / "mcp.servers.yaml" == cfg.MCP_SERVERS_YAML_PATH


def test_settings_default_paths_follow_fleetent_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setattr("fleetent.config.SETTINGS_YAML_PATH", tmp_path / "missing.yaml")

    s = Settings(anthropic_api_key="test-key")

    assert s.database_url == f"sqlite:///{tmp_path / 'data' / 'fleetent.db'}"
    assert s.observability.logging.directory == str(tmp_path / "data" / "logs")
