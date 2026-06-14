"""Compatibility tests for the legacy agent_oauth_binding_store import path."""

from __future__ import annotations

import pytest

import fleetent.agent_store as agent_store
from fleetent.platform.connector_management import agent_oauth_binding_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_bind_is_idempotent(store_db):
    agent = agent_store.create_agent("agent-5", "p", [])
    store.bind(agent.id, "github")
    store.bind(agent.id, "github")
    assert store.list_connectors_for_agent(agent.id) == ["github"]


def test_unbind_removes(store_db):
    agent = agent_store.create_agent("agent-5", "p", [])
    store.bind(agent.id, "github")
    store.unbind(agent.id, "github")
    assert store.list_connectors_for_agent(agent.id) == []


def test_scoped_per_agent(store_db):
    agent_a = agent_store.create_agent("agent-5", "p", [])
    agent_b = agent_store.create_agent("agent-7", "p", [])
    store.bind(agent_a.id, "github")
    store.bind(agent_b.id, "github")
    store.bind(agent_a.id, "jira")
    assert store.list_connectors_for_agent(agent_a.id) == ["github", "jira"]
    assert store.list_agents_for_connector("github") == [agent_a.id, agent_b.id]
