"""Integration tests for agent_runtime snapshot loading and request resolution.

Runtime resolution (``load_active``, ``resolve_agent_for_request``, ``connector_scope``,
``resolve_mcp_servers``) is file-sourced (file-driven-agent-config). Version-specific
loaders (``load_version``/``load_version_by_name``) stay DB-backed (authoring side).
"""

import dataclasses

import pytest
import yaml

import fleetent.agent_config as agent_config
import fleetent.agent_store as agent_store
import fleetent.runtime.snapshot as agent_runtime
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def agents(tmp_path):
    """A file agents dir wired as the current index; returns a writer that rescans."""
    root = tmp_path / "agents"
    root.mkdir()

    def write(name: str, **fields) -> None:
        doc = {
            "name": name,
            "version": 1,
            "models": agent_config.default_models().model_dump(mode="json"),
        }
        doc.update(fields)
        agent_dir = root / name
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        agent_config.scan(root)

    return write


def test_snapshot_is_frozen(agents):
    agents("a", system_prompt="P", allowed_tools=["shell"])
    snap = agent_runtime.load_active("a")
    assert snap is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.system_prompt = "mutated"  # type: ignore[misc]


def test_load_active_unpacks_file_fields(agents):
    agents(
        "analyst",
        version=3,
        system_prompt="You analyze.",
        allowed_tools=["shell", "github__*"],
        skills_dir="agents/analyst/skills",
        mcp_servers=[{"id": "github", "url": "https://gh"}],
        memory_namespace="analyst",
    )
    snap = agent_runtime.load_active("analyst")
    assert snap is not None
    assert snap.name == "analyst"
    assert snap.agent_id == "analyst"  # identity is the name (string)
    assert snap.version == 3
    assert snap.system_prompt == "You analyze."
    assert snap.allowed_tools == ["shell", "github__*"]
    assert snap.skills_dir == "agents/analyst/skills"
    assert snap.mcp_server_ids == ["github"]
    resolved = snap.model_policy.resolve("default")
    assert resolved[0].model == "default"
    assert resolved[1:] == ()
    assert snap.memory_namespace == "analyst"


def test_load_active_missing_returns_none(agents):
    agents("a", system_prompt="P", allowed_tools=["shell"])
    assert agent_runtime.load_active("nonexistent") is None


def test_load_active_reflects_file_version(agents):
    agents("a", version=2, system_prompt="v2 prompt", allowed_tools=["shell"])
    snap = agent_runtime.load_active("a")
    assert snap is not None
    assert snap.system_prompt == "v2 prompt"
    assert snap.version == 2


# --- version-specific loaders stay DB-backed (authoring side) ---


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


# --- resolve_agent_for_request: channel > user > default (file index) ---


def test_resolve_is_default_only_in_multi_agent_scan(agents):
    # bindings were removed from AgentFile; a multi-agent directory scan publishes no
    # default, so request resolution returns None regardless of channel/user inputs.
    agents("chan-bot", system_prompt="channel")
    agents("user-bot", system_prompt="user")
    snap = agent_runtime.resolve_agent_for_request("slack", "C1", "u1")
    assert snap is None


def test_resolve_returns_forced_default_in_single_agent_mode(tmp_path, monkeypatch):
    # Deployed single-agent mode (agents/default/agent.yaml under FLEETENT_HOME) is the
    # sole forced default; channel/user identifiers no longer influence resolution.
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    home_agent = tmp_path / "agents" / "default"
    home_agent.mkdir(parents=True)
    (home_agent / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "default",
                "version": 1,
                "system_prompt": "deployed",
                "models": agent_config.default_models().model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    agent_config.scan()
    try:
        snap = agent_runtime.resolve_agent_for_request("slack", "C-any", "u-any")
        assert snap is not None and snap.name == "default"
    finally:
        agent_config.scan(tmp_path / "nonexistent")  # drop the published index


def test_resolve_returns_none_when_nothing_matches(agents):
    agents("lonely", system_prompt="P")  # no bindings, no default
    assert agent_runtime.resolve_agent_for_request("slack", "C-none", "u-none") is None


# --- effective MCP server set + connector scope (file inline, zero DB) ---


def test_resolve_mcp_servers_overlays_inline_on_defaults(agents):
    agents(
        "a",
        system_prompt="P",
        mcp_servers=[{"id": "github", "transport": "http", "url": "https://agent-gh"}],
    )
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


def test_connector_scope_is_agent_name(agents):
    agents("a", system_prompt="P")
    snap = agent_runtime.load_active("a")
    assert snap is not None
    assert agent_runtime.connector_scope(snap) == "a"


def test_filter_tool_schemas_visibility_unchanged(agents):
    schemas = [
        {"function": {"name": "github__x"}},
        {"function": {"name": "jira__y"}},
        {"function": {"name": "shell"}},
    ]
    out = {
        s["function"]["name"] for s in agent_runtime.filter_tool_schemas(schemas, None, ["github"])
    }
    assert out == {"github__x", "shell"}
