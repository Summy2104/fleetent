from __future__ import annotations

import pytest


def _set_required_env(monkeypatch, *, platform_url: str, node_id: str, service_key: str) -> None:
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", platform_url)
    monkeypatch.setenv("FLEETENT_NODE_ID", node_id)
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", service_key)


def test_load_config_from_env(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    _set_required_env(
        monkeypatch,
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
    )
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

    _set_required_env(
        monkeypatch,
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
    )
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(config.ConfigError, match=expected_message):
        config.load_config()


def test_load_config_reads_node_env_file(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    for name in (
        "FLEETENT_NODE_PLATFORM_URL",
        "FLEETENT_NODE_ID",
        "FLEETENT_NODE_SERVICE_KEY",
        "FLEETENT_NODE_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    node_dir = tmp_path / "node"
    node_dir.mkdir()
    (node_dir / ".env").write_text(
        "\n".join(
            [
                "FLEETENT_NODE_PLATFORM_URL=https://from-file.internal/",
                "FLEETENT_NODE_ID=node-from-file",
                "FLEETENT_NODE_SERVICE_KEY=ma-" + "2" * 64,
                "FLEETENT_NODE_INTERVAL_SECONDS=22",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = config.load_config()

    assert loaded.platform_url == "https://from-file.internal"
    assert loaded.node_id == "node-from-file"
    assert loaded.service_key == "ma-" + "2" * 64
    assert loaded.home_dir == tmp_path
    assert loaded.interval_seconds == 22


def test_process_env_overrides_node_env(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    _set_required_env(
        monkeypatch,
        platform_url="https://from-process.internal/",
        node_id="node-from-process",
        service_key="ma-" + "3" * 64,
    )
    monkeypatch.setenv("FLEETENT_NODE_INTERVAL_SECONDS", "31")
    node_dir = tmp_path / "node"
    node_dir.mkdir()
    (node_dir / ".env").write_text(
        "\n".join(
            [
                "FLEETENT_NODE_PLATFORM_URL=https://from-file.internal/",
                "FLEETENT_NODE_ID=node-from-file",
                "FLEETENT_NODE_SERVICE_KEY=ma-" + "4" * 64,
                "FLEETENT_NODE_INTERVAL_SECONDS=44",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = config.load_config()

    assert loaded.platform_url == "https://from-process.internal"
    assert loaded.node_id == "node-from-process"
    assert loaded.service_key == "ma-" + "3" * 64
    assert loaded.interval_seconds == 31


def test_missing_node_env_falls_back_to_process_env(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    _set_required_env(
        monkeypatch,
        platform_url="https://process-only.internal",
        node_id="node-process-only",
        service_key="ma-" + "5" * 64,
    )

    loaded = config.load_config()

    assert loaded.platform_url == "https://process-only.internal"
    assert loaded.node_id == "node-process-only"
    assert loaded.service_key == "ma-" + "5" * 64
    assert loaded.home_dir == tmp_path


def test_missing_required_still_raises(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    for name in (
        "FLEETENT_NODE_PLATFORM_URL",
        "FLEETENT_NODE_ID",
        "FLEETENT_NODE_SERVICE_KEY",
        "FLEETENT_NODE_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(config.ConfigError, match="FLEETENT_NODE_PLATFORM_URL"):
        config.load_config()
