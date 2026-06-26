"""Unit tests: node advertise_host config (FLEETENT_NODE_ADVERTISE_HOST)."""

from __future__ import annotations


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)


def test_load_config_reads_advertise_host(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    _set_required_env(monkeypatch)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setenv("FLEETENT_NODE_ADVERTISE_HOST", "10.38.8.143")

    loaded = config.load_config()

    assert loaded.advertise_host == "10.38.8.143"


def test_load_config_advertise_host_defaults_none(monkeypatch, tmp_path) -> None:
    from fleetent.node import config

    _set_required_env(monkeypatch)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_NODE_ADVERTISE_HOST", raising=False)

    loaded = config.load_config()

    assert loaded.advertise_host is None
