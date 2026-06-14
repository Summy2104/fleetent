"""Tests for agent_admin_store (migration 015)."""

import sqlite3

import pytest

from fleetent import agent_store
from fleetent.platform.agent_management_console import agent_admin_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def agent_id(store_db):
    return agent_store.create_agent("ops", "Ops.", ["shell"]).id


def test_migration_creates_table(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_admin_state" in tables


def test_default_state(store_db):
    s = store.get_state(999)
    assert s["agent_id"] == 999
    assert s["agent_name"] is None
    assert s["status"] == "enabled"
    assert s["provenance"] == "adhoc"
    assert s["drift"] == 0


def test_enable_disable(store_db, agent_id):
    store.disable(agent_id)
    assert store.get_state(agent_id)["status"] == "disabled"
    store.enable(agent_id)
    assert store.get_state(agent_id)["status"] == "enabled"


def test_archive_records_timestamp_and_restore(store_db, agent_id):
    store.archive(agent_id)
    s = store.get_state(agent_id)
    assert s["status"] == "archived" and s["archived_at"] is not None
    store.restore(agent_id)
    assert store.get_state(agent_id)["status"] == "enabled"


def test_status_rejects_unknown(store_db, agent_id):
    with pytest.raises(ValueError):
        store.set_status(agent_id, "bogus")


def test_drift_only_for_managed(store_db):
    adhoc = agent_store.create_agent("adhoc-agent", "Adhoc.", ["shell"]).id
    managed = agent_store.create_agent("managed-agent", "Managed.", ["shell"]).id
    store.mark_drift(adhoc)  # adhoc → no-op
    assert store.get_state(adhoc)["drift"] == 0
    store.set_provenance(managed, "managed")
    store.mark_drift(managed)
    assert store.get_state(managed)["drift"] == 1
    store.clear_drift(managed)
    assert store.get_state(managed)["drift"] == 0


def test_provenance_flip_preserves_status_and_drift(store_db):
    # provenance lives in the side table keyed by name; flipping it must not disturb the
    # agent's lifecycle status or drift flag (identity/version/bindings live elsewhere).
    agent_id = agent_store.create_agent("svc", "Svc.", ["shell"]).id
    store.set_provenance(agent_id, "managed")
    store.disable(agent_id)
    store.mark_drift(agent_id)
    store.set_provenance(agent_id, "adhoc")  # flip back
    s = store.get_state(agent_id)
    assert s["agent_name"] == "svc"
    assert s["provenance"] == "adhoc"
    assert s["status"] == "disabled"  # unchanged
    assert s["drift"] == 1  # unchanged


def test_list_excludes_archived(store_db):
    a = agent_store.create_agent("a", "A.", ["shell"]).id
    b = agent_store.create_agent("b", "B.", ["shell"]).id
    store.enable(a)
    store.archive(b)
    visible = {s["agent_name"] for s in store.list_states()}
    assert "a" in visible and "b" not in visible


def test_references_and_protection(store_db):
    conn = sqlite3.connect(store_db)
    conn.execute("INSERT INTO user_agents (user_id, agent_id) VALUES ('u1', 7)")
    conn.commit()
    conn.close()
    refs = store.references(7)
    assert refs["users"] == ["u1"]
    assert refs["channels"] == []
    assert store.is_referenced(7) is True
    assert store.is_referenced(999) is False


def test_delete_state_removes_row(store_db):
    agent_id = agent_store.create_agent("gone", "Gone.", ["shell"]).id
    store.set_provenance(agent_id, "adhoc")
    store.enable(agent_id)
    assert any(s["agent_name"] == "gone" for s in store.list_states())
    store.delete_state(agent_id)
    assert all(s["agent_name"] != "gone" for s in store.list_states())


def test_delete_state_missing_is_noop(store_db):
    store.delete_state(999)  # must not raise
