from __future__ import annotations

import json
import sqlite3

import pytest
from cryptography.fernet import Fernet

from fleetent import agent_store
from fleetent.secret_crypto import SecretKeyError
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(db_path)
    return db_path


def test_register_returns_plaintext_once_and_stores_hash(db_path) -> None:
    from fleetent.platform.node_management import node_store

    plaintext, node = node_store.register_node(
        "node-eu-1",
        name="EU Node 1",
        labels={"region": "eu", "tier": "prod"},
    )

    assert plaintext.startswith("ma-")
    assert node["id"] == "node-eu-1"
    assert node["name"] == "EU Node 1"
    assert node["labels"] == {"region": "eu", "tier": "prod"}
    assert node["last_seen_at"] is None

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, name, key_hash, labels, registered_at, last_seen_at
            FROM nodes
            WHERE id = ?
            """,
            ("node-eu-1",),
        ).fetchone()

    assert row is not None
    assert row[0] == "node-eu-1"
    assert row[1] == "EU Node 1"
    assert row[2] != plaintext
    assert json.loads(str(row[3])) == {"region": "eu", "tier": "prod"}
    assert row[4] == node["registered_at"]
    assert row[5] is None


def test_register_duplicate_node_id_raises_value_error(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-eu-1")

    with pytest.raises(ValueError, match="already exists"):
        node_store.register_node("node-eu-1")


def test_resolve_node_key_returns_node_identity(db_path) -> None:
    from fleetent.platform.node_management import node_store

    plaintext, _ = node_store.register_node("node-ap-1", labels={"region": "apac"})

    resolved = node_store.resolve_node_key(plaintext)

    assert resolved is not None
    assert resolved["id"] == "node-ap-1"
    assert resolved["labels"] == {"region": "apac"}
    assert resolved["key_hash"] not in {None, plaintext}
    assert node_store.resolve_node_key("ma-" + "0" * 64) is None


def test_list_nodes_returns_registered_nodes(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-b", name="Node B")
    node_store.register_node("node-a", name="Node A")

    rows = node_store.list_nodes()

    assert [row["id"] for row in rows] == ["node-a", "node-b"]
    assert [row["name"] for row in rows] == ["Node A", "Node B"]


def test_deregister_idle_node_deletes_row(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-idle")

    node_store.deregister_node("node-idle")

    assert node_store.list_nodes() == []


def test_deregister_occupied_node_raises_value_error(db_path) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-busy")
    agent = agent_store.create_agent("ops", "Ops.", ["shell"])

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_placements (agent_id, node_id, pinned_at, pinned_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                agent.id,
                "node-busy",
                "2026-06-16T00:00:00+00:00",
                "seed",
                "2026-06-16T00:00:00+00:00",
            ),
        )
        conn.commit()

    with pytest.raises(ValueError, match="still has pinned agents"):
        node_store.deregister_node("node-busy")


def test_register_node_raises_and_leaves_no_record_when_key_persist_fails(
    db_path, monkeypatch
) -> None:
    from fleetent.platform.node_management import node_store

    # Simulate secret persist failure (e.g. missing master key)
    monkeypatch.delenv("FLEETENT_SECRET_KEY", raising=False)

    with pytest.raises(SecretKeyError):
        node_store.register_node("node-fail")

    # Must not leave a half-committed node row
    assert node_store.list_nodes() == []
