"""Integration tests for directed-reach identity layer.

Covers:
- im_gateway_management.resolve_user_addresses (reverse lookup)
- POST /nodes/{node_id}/identity/addresses endpoint
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

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


# ---------------------------------------------------------------------------
# Task 1.1 / 1.2 — resolve_user_addresses
# ---------------------------------------------------------------------------


def test_resolve_user_addresses_returns_all_bindings(db_path) -> None:
    from fleetent.platform import im_gateway_management

    # provision a user with two IM bindings
    user = im_gateway_management.resolve_or_provision(
        "default",
        verified_email="alice@example.com",
        channel="slack",
        platform_user_id="U_slack",
    )
    im_gateway_management.attach_identity("telegram", "TG_123", user.id)

    addresses = im_gateway_management.resolve_user_addresses(user.id)

    platforms = {a["platform"] for a in addresses}
    puid_map = {a["platform"]: a["platform_user_id"] for a in addresses}
    assert platforms == {"slack", "telegram"}
    assert puid_map["slack"] == "U_slack"
    assert puid_map["telegram"] == "TG_123"


def test_resolve_user_addresses_returns_empty_for_unbound_user(db_path) -> None:
    import fleetent.user_store as user_store

    user, _ = user_store.create_user("bob", tenant_id="default")
    from fleetent.platform import im_gateway_management

    addresses = im_gateway_management.resolve_user_addresses(user.id)
    assert addresses == []


# ---------------------------------------------------------------------------
# Task 1.3 / 1.4 — POST /nodes/{node_id}/identity/addresses
# ---------------------------------------------------------------------------


def test_post_identity_addresses_returns_bindings(node_client: TestClient, db_path) -> None:
    from fleetent.platform import im_gateway_management
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")

    user = im_gateway_management.resolve_or_provision(
        "default",
        verified_email="charlie@example.com",
        channel="slack",
        platform_user_id="U_charlie",
    )

    response = node_client.post(
        "/nodes/node-a/identity/addresses",
        headers={"Authorization": f"Bearer {node_key}"},
        json={"user_id": user.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["addresses"], list)
    assert len(payload["addresses"]) == 1
    assert payload["addresses"][0]["platform"] == "slack"
    assert payload["addresses"][0]["platform_user_id"] == "U_charlie"


def test_post_identity_addresses_returns_empty_for_unbound_user(
    node_client: TestClient, db_path
) -> None:
    import fleetent.user_store as user_store
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")
    user, _ = user_store.create_user("dave", tenant_id="default")

    response = node_client.post(
        "/nodes/node-a/identity/addresses",
        headers={"Authorization": f"Bearer {node_key}"},
        json={"user_id": user.id},
    )

    assert response.status_code == 200
    assert response.json()["addresses"] == []


def test_post_identity_addresses_rejects_missing_key(node_client: TestClient, db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-a")

    response = node_client.post(
        "/nodes/node-a/identity/addresses",
        json={"user_id": "some-user"},
    )
    assert response.status_code == 401


def test_post_identity_addresses_rejects_bad_key(node_client: TestClient, db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-a")

    response = node_client.post(
        "/nodes/node-a/identity/addresses",
        headers={"Authorization": "Bearer ma-" + "0" * 64},
        json={"user_id": "some-user"},
    )
    assert response.status_code == 401
