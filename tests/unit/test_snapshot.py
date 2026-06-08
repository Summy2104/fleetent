"""Unit tests for fleetent.runtime.snapshot: snapshot resolution and MCP merging."""

from typing import Any

from fleetent import agent_config, agent_store
from fleetent.agent_config import AgentConfigIndex, AgentFile
from fleetent.agent_store import AgentVersion
from fleetent.config import McpServerSettings
from fleetent.runtime import snapshot


def _agent_file(**overrides: Any) -> AgentFile:
    base: dict[str, Any] = {
        "name": "support",
        "version": 3,
        "system_prompt": "be helpful",
        "allowed_tools": ["read_file"],
        "skills_dir": "skills",
        "models": {
            "targets": [
                {
                    "id": "primary",
                    "provider": "anthropic",
                    "protocol": "openai_chat",
                    "base_url": "https://api.anthropic.com/v1/",
                    "model": "claude-sonnet",
                }
            ],
            "routes": {"default": [{"target": "primary"}]},
        },
        "memory_namespace": "support-ns",
    }
    base.update(overrides)
    return AgentFile(**base)


def _version(**overrides: Any) -> AgentVersion:
    base: dict[str, Any] = {
        "id": 99,
        "agent_id": 7,
        "version": 5,
        "system_prompt": "db prompt",
        "allowed_tools": ["search"],
        "skills_dir": None,
        "mcp_server_ids": ["github"],
        "model_overrides": {},
        "memory_namespace": "ns",
        "created_at": "2026-01-01T00:00:00Z",
        "is_active": True,
    }
    base.update(overrides)
    return AgentVersion(**base)


def _index(**overrides: Any) -> AgentConfigIndex:
    base: dict[str, Any] = {
        "agents": {},
        "default": None,
    }
    base.update(overrides)
    return AgentConfigIndex(**base)


# --- file-sourced snapshots -------------------------------------------------


def test_snapshot_from_file_maps_fields_and_mcp() -> None:
    agent = _agent_file(mcp_servers=[McpServerSettings(id="github"), McpServerSettings(id="slack")])
    snap = snapshot._snapshot_from_file(agent)
    assert snap.agent_id == "support"
    assert snap.name == "support"
    assert snap.version == 3
    assert snap.version_id == 3
    assert snap.system_prompt == "be helpful"
    assert snap.allowed_tools == ["read_file"]
    assert snap.skills_dir == "skills"
    assert snap.mcp_server_ids == ["github", "slack"]
    assert snap.memory_namespace == "support-ns"
    assert snap.model_policy.agent_id == "support"
    assert snap.model_policy.resolve("default")[0].target_id == "primary"
    assert not hasattr(snap, "model_overrides")


def test_snapshot_from_file_no_mcp_servers_yields_none() -> None:
    snap = snapshot._snapshot_from_file(_agent_file(mcp_servers=[]))
    assert snap.mcp_server_ids is None


def test_load_active_returns_snapshot(monkeypatch: Any) -> None:
    agent = _agent_file()
    monkeypatch.setattr(agent_config, "current", lambda: _index(agents={"support": agent}))
    snap = snapshot.load_active("support")
    assert snap is not None
    assert snap.name == "support"


def test_load_active_missing_returns_none(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_config, "current", lambda: _index())
    assert snapshot.load_active("ghost") is None


# --- DB-backed snapshots ----------------------------------------------------


def test_snapshot_from_version_maps_fields() -> None:
    snap = snapshot._snapshot("support", _version())
    assert snap.agent_id == "7"
    assert snap.name == "support"
    assert snap.version == 5
    assert snap.version_id == 99
    assert snap.system_prompt == "db prompt"
    assert snap.mcp_server_ids == ["github"]


def test_load_active_db_returns_active_version(monkeypatch: Any) -> None:
    inactive = _version(id=1, is_active=False)
    active = _version(id=2, is_active=True)
    monkeypatch.setattr(agent_store, "list_versions", lambda name: [inactive, active])
    snap = snapshot.load_active_db("support")
    assert snap is not None
    assert snap.version_id == 2


def test_load_active_db_none_when_no_active(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "list_versions", lambda name: [_version(is_active=False)])
    assert snapshot.load_active_db("support") is None


def test_load_version_by_name_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "get_by_name_version", lambda name, v: _version(version=v))
    snap = snapshot.load_version_by_name("support", 5)
    assert snap is not None and snap.version == 5


def test_load_version_by_name_not_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "get_by_name_version", lambda name, v: None)
    assert snapshot.load_version_by_name("support", 5) is None


def test_load_version_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "get_version_by_id", lambda vid: _version(id=vid))
    monkeypatch.setattr(agent_store, "get_agent_name_by_id", lambda aid: "support")
    snap = snapshot.load_version(99)
    assert snap is not None
    assert snap.version_id == 99
    assert snap.name == "support"


def test_load_version_none_when_version_missing(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "get_version_by_id", lambda vid: None)
    assert snapshot.load_version(99) is None


def test_load_version_none_when_name_missing(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_store, "get_version_by_id", lambda vid: _version())
    monkeypatch.setattr(agent_store, "get_agent_name_by_id", lambda aid: None)
    assert snapshot.load_version(99) is None


# --- request resolution -----------------------------------------------------


def test_resolve_agent_prefers_named_agent(monkeypatch: Any) -> None:
    # When msg.agent_name is set, the snapshot is resolved directly by name.
    agent = _agent_file(name="chan")
    index = _index(agents={"chan": agent, "def": _agent_file(name="def")}, default="def")
    monkeypatch.setattr(agent_config, "current", lambda: index)
    snap = snapshot.resolve_agent_for_request("slack", "C1", "u1")
    # resolve_agent_for_request uses default path (no bindings-based routing)
    assert snap is not None and snap.name == "def"


def test_resolve_agent_falls_back_to_default(monkeypatch: Any) -> None:
    agent = _agent_file(name="def")
    index = _index(agents={"def": agent}, default="def")
    monkeypatch.setattr(agent_config, "current", lambda: index)
    snap = snapshot.resolve_agent_for_request("slack", "C9", "u1")
    assert snap is not None and snap.name == "def"


def test_resolve_agent_falls_back_to_default(monkeypatch: Any) -> None:
    agent = _agent_file(name="def")
    index = _index(agents={"def": agent}, default="def")
    monkeypatch.setattr(agent_config, "current", lambda: index)
    snap = snapshot.resolve_agent_for_request(None, None, "unknown")
    assert snap is not None and snap.name == "def"


def test_resolve_agent_none_when_nothing_matches(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_config, "current", lambda: _index())
    assert snapshot.resolve_agent_for_request(None, None, None) is None


# --- MCP merge --------------------------------------------------------------


def test_resolve_mcp_servers_overlays_agent_on_defaults(monkeypatch: Any) -> None:
    agent = _agent_file(
        name="support",
        mcp_servers=[McpServerSettings(id="github", url="http://agent")],
    )
    monkeypatch.setattr(agent_config, "current", lambda: _index(agents={"support": agent}))
    defaults = [{"id": "github", "url": "http://default"}, {"id": "jira"}]
    snap = snapshot._snapshot_from_file(agent)
    merged = snapshot.resolve_mcp_servers(snap, defaults)
    ids = [s["id"] for s in merged]
    assert ids == ["github", "jira"]  # sorted by id
    github = next(s for s in merged if s["id"] == "github")
    assert github["url"] == "http://agent"  # agent definition wins


def test_resolve_mcp_servers_unknown_agent_returns_defaults(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_config, "current", lambda: _index())
    snap = snapshot._snapshot_from_file(_agent_file(name="support"))
    merged = snapshot.resolve_mcp_servers(snap, [{"id": "jira"}])
    assert [s["id"] for s in merged] == ["jira"]


def test_connector_scope_is_agent_id() -> None:
    snap = snapshot._snapshot_from_file(_agent_file(name="support"))
    assert snapshot.connector_scope(snap) == "support"


# --- tool schema filtering --------------------------------------------------


def _schema(name: str) -> dict[str, Any]:
    return {"function": {"name": name}}


def test_is_mcp_tool_detects_double_underscore() -> None:
    assert snapshot._is_mcp_tool("github__create_issue") is True
    assert snapshot._is_mcp_tool("read_file") is False


def test_filter_tool_schemas_no_restrictions_keeps_all() -> None:
    schemas = [_schema("read_file"), _schema("github__issue")]
    assert snapshot.filter_tool_schemas(schemas, None, None) == schemas


def test_filter_tool_schemas_allowlist_drops_unmatched() -> None:
    schemas = [_schema("read_file"), _schema("write_file")]
    result = snapshot.filter_tool_schemas(schemas, ["read_*"], None)
    assert [s["function"]["name"] for s in result] == ["read_file"]


def test_filter_tool_schemas_empty_mcp_list_drops_all_mcp() -> None:
    schemas = [_schema("read_file"), _schema("github__issue")]
    result = snapshot.filter_tool_schemas(schemas, None, [])
    assert [s["function"]["name"] for s in result] == ["read_file"]


def test_filter_tool_schemas_mcp_whitelist_keeps_listed_server() -> None:
    schemas = [
        _schema("read_file"),
        _schema("github__issue"),
        _schema("slack__post"),
    ]
    result = snapshot.filter_tool_schemas(schemas, None, ["github"])
    names = [s["function"]["name"] for s in result]
    assert names == ["read_file", "github__issue"]


# --- governance carried on the snapshot (runtime-read-agent-config) ---------


def test_snapshot_from_file_carries_governance() -> None:
    agent = _agent_file(agent_max_turns=30, tool_default_timeout_seconds=15.0)
    snap = snapshot._snapshot_from_file(agent)
    assert snap.governance.agent_max_turns == 30
    assert snap.governance.tool_default_timeout_seconds == 15.0


def test_snapshot_from_file_governance_defaults_match_settings() -> None:
    snap = snapshot._snapshot_from_file(_agent_file())
    g = snap.governance
    assert g.agent_max_turns == 50
    assert g.tool_default_timeout_seconds == 30.0
    assert g.agent_max_tokens == -1
    assert g.guardrail_repeat_threshold == 3
    assert g.agent_tool_parallel_max == 8
    assert g.agent_loop_repeat_threshold == 3
    assert g.loop_detect_ignore_arg_keys == ()


def test_db_snapshot_carries_default_governance() -> None:
    snap = snapshot._snapshot("support", _version())
    # DB/authoring side gets the prior Settings-equivalent defaults.
    assert snap.governance.agent_max_turns == 50
    assert snap.governance.tool_default_timeout_seconds == 30.0
