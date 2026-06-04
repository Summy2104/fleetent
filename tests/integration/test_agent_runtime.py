"""Integration tests for agent_runtime snapshot loading and request resolution."""

import dataclasses
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store
import fleetent.runtime.snapshot as agent_runtime


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_snapshot_is_frozen(db):
    agent_store.create_agent("a", "P", ["shell"])
    snap = agent_runtime.load_active("a")
    assert snap is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.system_prompt = "mutated"  # type: ignore[misc]


def test_load_active_unpacks_version_fields(db):
    agent_store.create_agent(
        "analyst",
        "You analyze.",
        ["shell", "github__*"],
        skills_dir="agents/analyst/skills",
        mcp_server_ids=["github"],
        model_overrides={"default": {"model": "x"}},
        memory_namespace="analyst",
    )
    snap = agent_runtime.load_active("analyst")
    assert snap is not None
    assert snap.name == "analyst"
    assert snap.version == 1
    assert snap.system_prompt == "You analyze."
    assert snap.allowed_tools == ["shell", "github__*"]
    assert snap.skills_dir == "agents/analyst/skills"
    assert snap.mcp_server_ids == ["github"]
    assert snap.model_overrides == {"default": {"model": "x"}}
    assert snap.memory_namespace == "analyst"


def test_load_active_missing_returns_none(db):
    assert agent_runtime.load_active("nonexistent") is None


def test_load_active_reflects_active_version(db):
    agent_store.create_agent("a", "v1 prompt", ["shell"])
    agent_store.create_version("a", system_prompt="v2 prompt")
    snap = agent_runtime.load_active("a")
    assert snap is not None
    assert snap.system_prompt == "v2 prompt"
    assert snap.version == 2


def test_load_version_by_name_returns_specific(db):
    agent_store.create_agent("a", "v1 prompt", ["shell"])
    agent_store.create_version("a", system_prompt="v2 prompt")
    v1 = agent_runtime.load_version_by_name("a", 1)
    assert v1 is not None and v1.system_prompt == "v1 prompt" and v1.version == 1
    assert agent_runtime.load_version_by_name("a", 99) is None
    assert agent_runtime.load_version_by_name("missing", 1) is None


def test_load_version_by_id(db):
    agent_store.create_agent("a", "v1 prompt", ["shell"])
    v2 = agent_store.create_version("a", system_prompt="v2 prompt", activate=False)
    snap = agent_runtime.load_version(v2.id)
    assert snap is not None
    assert snap.name == "a"
    assert snap.version == v2.version
    assert snap.system_prompt == "v2 prompt"
    assert agent_runtime.load_version(999999) is None


# --- resolve_agent_for_request: channel > user > default ---


def test_resolve_prefers_channel_over_user_and_default(db, monkeypatch):
    chan = agent_store.create_agent("chan-bot", "channel", ["shell"])
    user_agent = agent_store.create_agent("user-bot", "user", ["shell"])
    agent_store.create_agent("default-bot", "default", ["shell"])
    agent_store.assign_channel("slack", "C1", chan.id)
    agent_store.assign_user("u1", user_agent.id)
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "default-bot")

    snap = agent_runtime.resolve_agent_for_request("slack", "C1", "u1")
    assert snap is not None and snap.name == "chan-bot"


def test_resolve_falls_back_to_user_when_no_channel(db, monkeypatch):
    user_agent = agent_store.create_agent("user-bot", "user", ["shell"])
    agent_store.create_agent("default-bot", "default", ["shell"])
    agent_store.assign_user("u1", user_agent.id)
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "default-bot")

    snap = agent_runtime.resolve_agent_for_request("slack", "C-none", "u1")
    assert snap is not None and snap.name == "user-bot"


def test_resolve_falls_back_to_default_when_no_channel_or_user(db, monkeypatch):
    agent_store.create_agent("default-bot", "default", ["shell"])
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "default-bot")

    snap = agent_runtime.resolve_agent_for_request("slack", "C-none", "u-none")
    assert snap is not None and snap.name == "default-bot"


def test_resolve_returns_none_when_nothing_matches(db, monkeypatch):
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: None)
    assert agent_runtime.resolve_agent_for_request("slack", "C-none", "u-none") is None


# --- effective MCP server set + connector scope ---


def test_resolve_mcp_servers_overlays_agent_owned_on_defaults(db):
    from fleetent.platform.connector_management import agent_mcp_server_store

    a = agent_store.create_agent("a", "P", ["shell"])
    agent_mcp_server_store.add_mcp_server(a.id, "github", transport="http", url="https://agent-gh")
    snap = agent_runtime.load_active("a")
    assert snap is not None
    defaults = [
        {"id": "github", "transport": "http", "url": "https://default-gh"},
        {"id": "slack", "transport": "http", "url": "https://default-slack"},
    ]
    resolved = {s["id"]: s for s in agent_runtime.resolve_mcp_servers(snap, defaults)}
    assert set(resolved) == {"github", "slack"}
    assert resolved["github"]["url"] == "https://agent-gh"
    assert resolved["slack"]["url"] == "https://default-slack"


def test_connector_scope_is_agent_id(db):
    a = agent_store.create_agent("a", "P", ["shell"])
    snap = agent_runtime.load_active("a")
    assert snap is not None
    assert agent_runtime.connector_scope(snap) == a.id


def test_filter_tool_schemas_visibility_unchanged(db):
    schemas = [
        {"function": {"name": "github__x"}},
        {"function": {"name": "jira__y"}},
        {"function": {"name": "shell"}},
    ]
    out = {
        s["function"]["name"] for s in agent_runtime.filter_tool_schemas(schemas, None, ["github"])
    }
    assert out == {"github__x", "shell"}
