"""Tests for per-agent MCP server bindings in agent_store.

Schema created by Alembic migrations against a tmp_path database, isolated via the
DATABASE_URL env var (named params, no legacy _init_db / DB_PATH path).
"""

import pytest

import fleetent.agent_store as agent_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_bind_and_list_mcp_server(db):
    agent = agent_store.create_agent("support", "You help.", ["shell"])
    agent_store.bind_mcp_server(agent.id, "github")
    assert agent_store.list_mcp_servers_for_agent(agent.id) == ["github"]


def test_bind_is_idempotent(db):
    agent = agent_store.create_agent("support", "You help.", ["shell"])
    agent_store.bind_mcp_server(agent.id, "github")
    agent_store.bind_mcp_server(agent.id, "github")
    assert agent_store.list_mcp_servers_for_agent(agent.id) == ["github"]


def test_unbind_mcp_server(db):
    agent = agent_store.create_agent("support", "You help.", ["shell"])
    agent_store.bind_mcp_server(agent.id, "github")
    agent_store.bind_mcp_server(agent.id, "jira")
    agent_store.unbind_mcp_server(agent.id, "github")
    assert agent_store.list_mcp_servers_for_agent(agent.id) == ["jira"]


def test_bind_does_not_mint_new_version(db):
    agent = agent_store.create_agent("support", "You help.", ["shell"])
    before = agent_store.list_versions("support")
    agent_store.bind_mcp_server(agent.id, "github")
    after = agent_store.list_versions("support")
    assert len(after) == len(before)
