from __future__ import annotations

import pytest

from fleetent import agent_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)
    return db_path


def test_pin_creates_and_replaces_agent_placement(migrated_db) -> None:
    from fleetent.platform.node_management import node_store, placement_store

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    node_store.register_node("node-a")
    node_store.register_node("node-b")

    placement_store.pin_agent(agent.id, "node-a", pinned_by="ops-admin")
    first = placement_store.get_for_agent(agent.id)
    placement_store.pin_agent(agent.id, "node-b", pinned_by="ops-admin")
    second = placement_store.get_for_agent(agent.id)

    assert first is not None
    assert first["node_id"] == "node-a"
    assert first["pinned_by"] == "ops-admin"
    assert second is not None
    assert second["node_id"] == "node-b"
    assert [row["agent_id"] for row in placement_store.list_by_node("node-a")] == []
    assert [row["agent_id"] for row in placement_store.list_by_node("node-b")] == [agent.id]


def test_pin_missing_agent_or_node_raises_value_error(migrated_db) -> None:
    from fleetent.platform.node_management import node_store, placement_store

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    node_store.register_node("node-a")

    with pytest.raises(ValueError, match="agent .* not found"):
        placement_store.pin_agent(agent.id + 999, "node-a")

    with pytest.raises(ValueError, match="node .* not found"):
        placement_store.pin_agent(agent.id, "node-missing")


def test_unpin_removes_agent_placement(migrated_db) -> None:
    from fleetent.platform.node_management import node_store, placement_store

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])
    node_store.register_node("node-a")
    placement_store.pin_agent(agent.id, "node-a")

    placement_store.unpin_agent(agent.id)

    assert placement_store.get_for_agent(agent.id) is None
    assert placement_store.list_by_node("node-a") == []
