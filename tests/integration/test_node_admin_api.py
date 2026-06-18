from __future__ import annotations

from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.user_store as user_store
from fleetent.server import app
from fleetent.platform.node_management import node_store, placement_store
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    apply_migrations(db_path)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def test_node_admin_routes_exist(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/admin/nodes", headers=_session_header("admin"))

    assert response.status_code == 200


def test_register_node_returns_service_key_once(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/nodes",
        headers=_session_header("admin"),
        json={"node_id": "node-a", "name": "Node A", "labels": {"region": "eu"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "node-a"
    assert body["service_key_plaintext_once"].startswith("ma-")
    assert "key_hash" not in body


def test_duplicate_node_id_returns_409(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    node_store.register_node("node-a")

    response = client.post(
        "/admin/nodes",
        headers=_session_header("admin"),
        json={"node_id": "node-a"},
    )

    assert response.status_code == 409


def test_list_nodes(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    node_store.register_node("node-b", name="Node B")
    node_store.register_node("node-a", name="Node A")

    response = client.get("/admin/nodes", headers=_session_header("admin"))

    assert response.status_code == 200
    assert [node["id"] for node in response.json()] == ["node-a", "node-b"]


def test_deregister_node_success(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    node_store.register_node("node-a")

    response = client.delete("/admin/nodes/node-a", headers=_session_header("admin"))

    assert response.status_code == 200
    assert node_store.get_node("node-a") is None


def test_deregister_pinned_node_returns_409(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    node_store.register_node("node-a")
    agent = agent_store.create_agent("ops", "Ops", ["shell"])
    placement_store.pin_agent(agent.id, "node-a")

    response = client.delete("/admin/nodes/node-a", headers=_session_header("admin"))

    assert response.status_code == 409


def test_pin_and_unpin_agent(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    node_store.register_node("node-a")
    agent = agent_store.create_agent("ops", "Ops", ["shell"])

    pin_response = client.post(
        "/admin/nodes/node-a/pin",
        headers=_session_header("admin"),
        json={"agent_id": agent.id, "pinned_by": "admin"},
    )

    assert pin_response.status_code == 200
    assert placement_store.get_for_agent(agent.id)["node_id"] == "node-a"

    unpin_response = client.delete(
        f"/admin/nodes/node-a/pin?agent_id={agent.id}",
        headers=_session_header("admin"),
    )

    assert unpin_response.status_code == 200
    assert placement_store.get_for_agent(agent.id) is None


def test_non_admin_returns_403(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/nodes",
        headers=_session_header("viewer"),
        json={"node_id": "node-a"},
    )

    assert response.status_code == 403
