"""Tests for agent_kbs_store: KB↔Agent binding matrix (migration 012, db runtime)."""

import sqlite3

import pytest

from fleetent import agent_store
from fleetent.platform.knowledge_base_management import agent_kbs_store as store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_table(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_kbs" in tables


def test_bind_and_list_both_directions(store_db):
    agent_a = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    agent_b = agent_store.create_agent("agent-b", "Prompt.", ["shell"])
    store.bind("default", "sales", agent_a.id, created_by="admin")
    store.bind("default", "sales", agent_b.id, created_by="admin")
    store.bind("default", "support", agent_a.id, created_by="admin")
    assert store.list_agents_for_kb("default", "sales") == [agent_a.id, agent_b.id]
    assert store.list_kbs_for_agent("default", agent_a.id) == ["sales", "support"]


def test_bind_is_idempotent(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    store.bind("default", "sales", agent.id)
    store.bind("default", "sales", agent.id)  # no error, no dup
    assert store.list_agents_for_kb("default", "sales") == [agent.id]


def test_is_kb_bound(store_db):
    assert store.is_kb_bound("default", "sales") is False
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    store.bind("default", "sales", agent.id)
    assert store.is_kb_bound("default", "sales") is True


def test_unbind(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    store.bind("default", "sales", agent.id)
    store.unbind("default", "sales", agent.id)
    assert store.is_kb_bound("default", "sales") is False


def test_tenancy_isolation(store_db):
    tenancy_store.create_tenant(id="t1", name="Tenant 1")
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"], tenant_id="t1")
    store.bind("t1", "sales", agent.id)
    assert store.is_kb_bound("t2", "sales") is False
    assert store.list_agents_for_kb("t2", "sales") == []


def test_integer_agent_id_crud(store_db):
    agent = agent_store.create_agent("agent-seven", "Prompt.", ["shell"])
    store.bind("default", "sales", agent.id, created_by="admin")
    store.bind("default", "support", agent.id, created_by="admin")

    assert store.list_agents_for_kb("default", "sales") == [agent.id]
    assert store.list_kbs_for_agent("default", agent.id) == ["sales", "support"]

    store.unbind("default", "sales", agent.id)

    assert store.list_agents_for_kb("default", "sales") == []
    assert store.list_kbs_for_agent("default", agent.id) == ["support"]
