"""Integration tests: node status heartbeat persists reported forward_host."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(db_path)
    return db_path


@pytest.fixture
def node_client(db_path) -> TestClient:
    from fleetent.platform.node_management import node_desired_state_api

    app = FastAPI()
    app.include_router(node_desired_state_api.router)
    return TestClient(app)


def test_status_with_forward_host_persists(node_client: TestClient) -> None:
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")

    response = node_client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {node_key}"},
        json={"agents": [], "forward_host": "10.38.8.143"},
    )

    assert response.status_code == 200
    assert node_store.get_forward_host("node-a") == "10.38.8.143"


def test_status_without_forward_host_parses_and_keeps_existing(node_client: TestClient) -> None:
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")
    node_store.set_forward_host("node-a", "10.0.0.5")

    # Old node payload omits forward_host: must still parse (200) and not clear the value.
    response = node_client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {node_key}"},
        json={"agents": []},
    )

    assert response.status_code == 200
    assert node_store.get_forward_host("node-a") == "10.0.0.5"
