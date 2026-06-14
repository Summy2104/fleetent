"""Integration tests for the agent service grant store."""

from __future__ import annotations

import importlib
import importlib.util

import pytest

import fleetent.agent_store as agent_store
from tests.integration._migration_template import apply_migrations


def _grant_store_module():
    spec = importlib.util.find_spec(
        "fleetent.platform.connector_management.agent_service_grant_store"
    )
    assert spec is not None, "agent_service_grant_store module is missing"
    return importlib.import_module("fleetent.platform.connector_management.agent_service_grant_store")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_bind_is_idempotent_and_defaults_run_as_user(store_db):
    store = _grant_store_module()
    agent = agent_store.create_agent("agent-5", "p", [])

    store.bind(agent.id, "github")
    store.bind(agent.id, "github")

    assert store.list_services_for_agent(agent.id) == [
        {"service_id": "github", "run_as": "user"}
    ]


def test_bind_accepts_explicit_run_as(store_db):
    store = _grant_store_module()
    agent = agent_store.create_agent("agent-5", "p", [])

    store.bind(agent.id, "github", run_as="agent")

    assert store.list_services_for_agent(agent.id) == [
        {"service_id": "github", "run_as": "agent"}
    ]


def test_unbind_and_reverse_lookup(store_db):
    store = _grant_store_module()
    agent_a = agent_store.create_agent("agent-5", "p", [])
    agent_b = agent_store.create_agent("agent-7", "p", [])
    store.bind(agent_a.id, "github")
    store.bind(agent_b.id, "github")
    store.bind(agent_a.id, "jira")

    assert store.list_agents_for_service("github") == [agent_a.id, agent_b.id]
    store.unbind(agent_a.id, "github")
    assert store.list_services_for_agent(agent_a.id) == [{"service_id": "jira", "run_as": "user"}]
