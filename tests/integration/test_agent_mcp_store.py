"""Tests for per-agent MCP server bindings in agent_store.

Schema created by Alembic migrations against a tmp_path database, isolated via the
DATABASE_URL env var (named params, no legacy _init_db / DB_PATH path).
"""

import sqlite3

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
    before = agent_store.get_by_name("support")
    agent_store.bind_mcp_server(agent.id, "github")
    after = agent_store.get_by_name("support")
    assert before is not None and after is not None
    assert after.version == before.version


def test_agent_mcp_approval_rules_round_trip(db):
    agent = agent_store.create_agent("support", "You help.", ["shell"])
    agent_store.bind_mcp_server(agent.id, "mailer")
    assert agent_store.get_agent_mcp_approval_rules(agent.id, "mailer") == []

    rules = [
        {"tool": "send_email", "when": {"operation": ["send"]}},
        {"tool": "delete_all", "when": None},
    ]
    agent_store.set_agent_mcp_approval_rules(agent.id, "mailer", rules)
    assert agent_store.get_agent_mcp_approval_rules(agent.id, "mailer") == rules

    # Rules are per-(agent, server): a second agent binding the same server starts empty.
    other = agent_store.create_agent("other", "x", ["shell"])
    agent_store.bind_mcp_server(other.id, "mailer")
    assert agent_store.get_agent_mcp_approval_rules(other.id, "mailer") == []


def test_migration_119_moves_approval_rules_column_to_binding(db):
    with sqlite3.connect(db) as conn:
        binding_cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_mcp_servers)")}
        server_cols = {r[1] for r in conn.execute("PRAGMA table_info(mcp_servers)")}
    assert "approval_rules" in binding_cols
    assert "approval_rules" not in server_cols
