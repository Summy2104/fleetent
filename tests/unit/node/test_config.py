from __future__ import annotations

import pytest


def test_load_config_from_env(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setenv("FLEETENT_NODE_INTERVAL_SECONDS", "15")

    loaded = config.load_config()

    assert loaded.platform_url == "https://platform.internal"
    assert loaded.node_id == "node-a"
    assert loaded.service_key == "ma-" + "1" * 64
    assert loaded.home_dir == tmp_path
    assert loaded.interval_seconds == 15


@pytest.mark.parametrize(
    ("missing_key", "expected_message"),
    [
        ("FLEETENT_NODE_PLATFORM_URL", "FLEETENT_NODE_PLATFORM_URL"),
        ("FLEETENT_NODE_ID", "FLEETENT_NODE_ID"),
        ("FLEETENT_NODE_SERVICE_KEY", "FLEETENT_NODE_SERVICE_KEY"),
    ],
)
def test_load_config_requires_mandatory_values(
    monkeypatch, tmp_path, missing_key: str, expected_message: str
) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(config.ConfigError, match=expected_message):
        config.load_config()
