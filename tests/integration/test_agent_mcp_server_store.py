"""Tests for agent_mcp_server_store (migration 034, db runtime). Per-agent MCP defs."""

import sqlite3

import pytest

from fleetent import agent_store
from fleetent.platform.connector_management import agent_mcp_server_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _create_agent(name: str) -> int:
    return agent_store.create_agent(name, f"{name} prompt", ["shell"]).id


def test_add_and_get_scoped(store_db):
    agent_id = _create_agent("agent-a")
    store.add_mcp_server(agent_id, "github", transport="stdio", command="npx", args=["-y", "gh"])
    s = store.get_mcp_server(agent_id, "github")
    assert s["server_id"] == "github"
    assert s["transport"] == "stdio"
    assert s["command"] == "npx"
    assert s["args"] == ["-y", "gh"]
    assert s["agent_id"] == agent_id


def test_get_returns_none_for_other_agent(store_db):
    owner_id = _create_agent("agent-owner")
    other_id = _create_agent("agent-other")
    store.add_mcp_server(owner_id, "github")
    assert store.get_mcp_server(other_id, "github") is None


def test_same_server_id_across_agents(store_db):
    left_id = _create_agent("agent-left")
    right_id = _create_agent("agent-right")
    store.add_mcp_server(left_id, "github", url="https://a")
    store.add_mcp_server(right_id, "github", url="https://b")
    assert store.get_mcp_server(left_id, "github")["url"] == "https://a"
    assert store.get_mcp_server(right_id, "github")["url"] == "https://b"


def test_duplicate_per_scope_rejected(store_db):
    agent_id = _create_agent("agent-dup")
    store.add_mcp_server(agent_id, "github")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_mcp_server(agent_id, "github")


def test_list_scoped(store_db):
    left_id = _create_agent("agent-list-left")
    right_id = _create_agent("agent-list-right")
    store.add_mcp_server(left_id, "github")
    store.add_mcp_server(left_id, "slack")
    store.add_mcp_server(right_id, "jira")
    assert {s["server_id"] for s in store.list_mcp_servers(left_id)} == {"github", "slack"}


def test_resolve_overlays_agent_on_defaults(store_db):
    defaults = [
        {"id": "github", "transport": "http", "url": "https://default-gh"},
        {"id": "slack", "transport": "http", "url": "https://default-slack"},
    ]
    agent_id = _create_agent("agent-resolve")
    store.add_mcp_server(agent_id, "github", transport="http", url="https://agent-gh")
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(agent_id, defaults)}
    assert set(resolved) == {"github", "slack"}
    assert resolved["github"]["url"] == "https://agent-gh"
    assert resolved["slack"]["url"] == "https://default-slack"


def test_resolve_adds_agent_only_server(store_db):
    defaults = [{"id": "github", "transport": "http", "url": "https://default-gh"}]
    agent_id = _create_agent("agent-add-only")
    store.add_mcp_server(agent_id, "internal", transport="stdio", command="python")
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(agent_id, defaults)}
    assert set(resolved) == {"github", "internal"}
    assert resolved["internal"]["command"] == "python"


def test_enabled_defaults_true(store_db):
    agent_id = _create_agent("agent-enabled")
    store.add_mcp_server(agent_id, "github")
    assert store.get_mcp_server(agent_id, "github")["enabled"] is True


def test_edit_updates_fields(store_db):
    agent_id = _create_agent("agent-edit")
    store.add_mcp_server(agent_id, "github", url="https://a", transport="http")
    store.edit_mcp_server(agent_id, "github", url="https://b", transport="websocket")
    s = store.get_mcp_server(agent_id, "github")
    assert s["url"] == "https://b"
    assert s["transport"] == "websocket"


def test_edit_can_disable(store_db):
    agent_id = _create_agent("agent-disable")
    store.add_mcp_server(agent_id, "github")
    store.edit_mcp_server(agent_id, "github", enabled=False)
    assert store.get_mcp_server(agent_id, "github")["enabled"] is False


def test_delete_removes_row(store_db):
    agent_id = _create_agent("agent-delete")
    store.add_mcp_server(agent_id, "github")
    store.delete_mcp_server(agent_id, "github")
    assert store.get_mcp_server(agent_id, "github") is None


def test_delete_is_scoped(store_db):
    left_id = _create_agent("agent-delete-left")
    right_id = _create_agent("agent-delete-right")
    store.add_mcp_server(left_id, "github")
    store.add_mcp_server(right_id, "github")
    store.delete_mcp_server(left_id, "github")
    assert store.get_mcp_server(left_id, "github") is None
    assert store.get_mcp_server(right_id, "github") is not None


def test_resolve_skips_disabled(store_db):
    defaults = [{"id": "github", "transport": "http", "url": "https://default-gh"}]
    agent_id = _create_agent("agent-skip-disabled")
    store.add_mcp_server(agent_id, "internal", transport="stdio", command="python", enabled=False)
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(agent_id, defaults)}
    assert set(resolved) == {"github"}


def test_headers_round_trip(store_db):
    agent_id = _create_agent("agent-headers")
    store.add_mcp_server(
        agent_id, "h1", transport="http", url="https://a", headers={"X-API-Key": "k"}
    )
    s = store.get_mcp_server(agent_id, "h1")
    assert s["headers"] == {"X-API-Key": "k"}


def test_headers_default_empty(store_db):
    agent_id = _create_agent("agent-headers-default")
    store.add_mcp_server(agent_id, "h2")
    assert store.get_mcp_server(agent_id, "h2")["headers"] == {}


def test_edit_headers(store_db):
    agent_id = _create_agent("agent-edit-headers")
    store.add_mcp_server(agent_id, "h3", headers={"A": "1"})
    store.edit_mcp_server(agent_id, "h3", headers={"B": "2"})
    assert store.get_mcp_server(agent_id, "h3")["headers"] == {"B": "2"}


def test_resolve_includes_headers(store_db):
    agent_id = _create_agent("agent-resolve-headers")
    store.add_mcp_server(
        agent_id, "h4", transport="http", url="https://a", headers={"X-API-Key": "k"}
    )
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(agent_id, [])}
    assert resolved["h4"]["headers"] == {"X-API-Key": "k"}
