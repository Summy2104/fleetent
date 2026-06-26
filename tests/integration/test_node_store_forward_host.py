"""Integration tests for node_store.forward_host read/write."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(db_path)
    return db_path


def test_forward_host_in_cols_and_defaults_null(db_path) -> None:
    from fleetent.platform.node_management import node_store

    assert "forward_host" in node_store._COLS
    node_store.register_node("node-1")
    assert node_store.get_forward_host("node-1") is None
    node = node_store.get_node("node-1")
    assert node is not None
    assert node["forward_host"] is None


def test_set_and_get_forward_host(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-1")
    node_store.set_forward_host("node-1", "10.0.0.5")

    assert node_store.get_forward_host("node-1") == "10.0.0.5"
    node = node_store.get_node("node-1")
    assert node is not None
    assert node["forward_host"] == "10.0.0.5"


def test_set_forward_host_unknown_node_does_not_insert(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.set_forward_host("ghost", "10.0.0.9")

    assert node_store.get_node("ghost") is None
    assert node_store.get_forward_host("ghost") is None


def test_set_forward_host_overwrites_with_latest(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-1")
    node_store.set_forward_host("node-1", "10.0.0.5")
    node_store.set_forward_host("node-1", "10.0.0.6")

    assert node_store.get_forward_host("node-1") == "10.0.0.6"
