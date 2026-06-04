"""Tests for agent_mcp_server_store (migration 034, db runtime). Per-agent MCP defs."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.connector_management import agent_mcp_server_store as store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_add_and_get_scoped(store_db):
    store.add_mcp_server(5, "github", transport="stdio", command="npx", args=["-y", "gh"])
    s = store.get_mcp_server(5, "github")
    assert s["server_id"] == "github"
    assert s["transport"] == "stdio"
    assert s["command"] == "npx"
    assert s["args"] == ["-y", "gh"]
    assert s["agent_id"] == 5


def test_get_returns_none_for_other_agent(store_db):
    store.add_mcp_server(5, "github")
    assert store.get_mcp_server(7, "github") is None


def test_same_server_id_across_agents(store_db):
    store.add_mcp_server(5, "github", url="https://a")
    store.add_mcp_server(7, "github", url="https://b")
    assert store.get_mcp_server(5, "github")["url"] == "https://a"
    assert store.get_mcp_server(7, "github")["url"] == "https://b"


def test_duplicate_per_scope_rejected(store_db):
    store.add_mcp_server(5, "github")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_mcp_server(5, "github")


def test_list_scoped(store_db):
    store.add_mcp_server(5, "github")
    store.add_mcp_server(5, "slack")
    store.add_mcp_server(7, "jira")
    assert {s["server_id"] for s in store.list_mcp_servers(5)} == {"github", "slack"}


def test_resolve_overlays_agent_on_defaults(store_db):
    defaults = [
        {"id": "github", "transport": "http", "url": "https://default-gh"},
        {"id": "slack", "transport": "http", "url": "https://default-slack"},
    ]
    store.add_mcp_server(5, "github", transport="http", url="https://agent-gh")
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(5, defaults)}
    assert set(resolved) == {"github", "slack"}
    assert resolved["github"]["url"] == "https://agent-gh"
    assert resolved["slack"]["url"] == "https://default-slack"


def test_resolve_adds_agent_only_server(store_db):
    defaults = [{"id": "github", "transport": "http", "url": "https://default-gh"}]
    store.add_mcp_server(5, "internal", transport="stdio", command="python")
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(5, defaults)}
    assert set(resolved) == {"github", "internal"}
    assert resolved["internal"]["command"] == "python"


def test_enabled_defaults_true(store_db):
    store.add_mcp_server(5, "github")
    assert store.get_mcp_server(5, "github")["enabled"] is True


def test_edit_updates_fields(store_db):
    store.add_mcp_server(5, "github", url="https://a", transport="http")
    store.edit_mcp_server(5, "github", url="https://b", transport="websocket")
    s = store.get_mcp_server(5, "github")
    assert s["url"] == "https://b"
    assert s["transport"] == "websocket"


def test_edit_can_disable(store_db):
    store.add_mcp_server(5, "github")
    store.edit_mcp_server(5, "github", enabled=False)
    assert store.get_mcp_server(5, "github")["enabled"] is False


def test_delete_removes_row(store_db):
    store.add_mcp_server(5, "github")
    store.delete_mcp_server(5, "github")
    assert store.get_mcp_server(5, "github") is None


def test_delete_is_scoped(store_db):
    store.add_mcp_server(5, "github")
    store.add_mcp_server(7, "github")
    store.delete_mcp_server(5, "github")
    assert store.get_mcp_server(5, "github") is None
    assert store.get_mcp_server(7, "github") is not None


def test_resolve_skips_disabled(store_db):
    defaults = [{"id": "github", "transport": "http", "url": "https://default-gh"}]
    store.add_mcp_server(5, "internal", transport="stdio", command="python", enabled=False)
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(5, defaults)}
    assert set(resolved) == {"github"}


def test_headers_round_trip(store_db):
    store.add_mcp_server(5, "h1", transport="http", url="https://a", headers={"X-API-Key": "k"})
    s = store.get_mcp_server(5, "h1")
    assert s["headers"] == {"X-API-Key": "k"}


def test_headers_default_empty(store_db):
    store.add_mcp_server(5, "h2")
    assert store.get_mcp_server(5, "h2")["headers"] == {}


def test_edit_headers(store_db):
    store.add_mcp_server(5, "h3", headers={"A": "1"})
    store.edit_mcp_server(5, "h3", headers={"B": "2"})
    assert store.get_mcp_server(5, "h3")["headers"] == {"B": "2"}


def test_resolve_includes_headers(store_db):
    store.add_mcp_server(5, "h4", transport="http", url="https://a", headers={"X-API-Key": "k"})
    resolved = {s["id"]: s for s in store.resolve_mcp_servers(5, [])}
    assert resolved["h4"]["headers"] == {"X-API-Key": "k"}
