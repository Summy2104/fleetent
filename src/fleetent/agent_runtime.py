"""Runtime resolution of agent configuration into an executable snapshot.

This module turns stored agent/version rows into the immutable ``AgentSnapshot``
the agent loop consumes, and provides the pure tool-schema filter that enforces
both the per-agent ``allowed_tools`` allowlist and the MCP server whitelist.

It never imports the agent loop (one-way dependency: agent_loop -> agent_runtime).
"""

from dataclasses import dataclass
from typing import Any

from fleetent import agent_store
from fleetent.agent_store import AgentVersion
from fleetent.governance.agent_policy import check_tool_access

ToolSchema = dict[str, Any]


@dataclass(frozen=True)
class AgentSnapshot:
    """Immutable, fully-resolved agent configuration the agent loop consumes."""

    agent_id: int
    name: str
    version: int
    version_id: int
    system_prompt: str
    allowed_tools: list[str]
    skills_dir: str | None
    mcp_server_ids: list[str] | None
    model_overrides: dict[str, Any]
    memory_namespace: str


def _snapshot(name: str, version: AgentVersion) -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=version.agent_id,
        name=name,
        version=version.version,
        version_id=version.id,
        system_prompt=version.system_prompt,
        allowed_tools=version.allowed_tools,
        skills_dir=version.skills_dir,
        mcp_server_ids=version.mcp_server_ids,
        model_overrides=version.model_overrides,
        memory_namespace=version.memory_namespace,
    )


def load_active(name: str) -> AgentSnapshot | None:
    """Resolve the agent's active version into a snapshot, or ``None`` if absent."""
    active = next((v for v in agent_store.list_versions(name) if v.is_active), None)
    return None if active is None else _snapshot(name, active)


def load_version_by_name(name: str, version: int) -> AgentSnapshot | None:
    ver = agent_store.get_by_name_version(name, version)
    return None if ver is None else _snapshot(name, ver)


def load_version(version_id: int) -> AgentSnapshot | None:
    ver = agent_store.get_version_by_id(version_id)
    if ver is None:
        return None
    name = agent_store.get_agent_name_by_id(ver.agent_id)
    return None if name is None else _snapshot(name, ver)


def resolve_agent_for_request(
    platform: str | None,
    channel_id: str | None,
    user_id: str | None,
) -> AgentSnapshot | None:
    """Resolve the agent for a request, strict precedence: channel > user > default."""
    if platform and channel_id:
        channel_agent = agent_store.get_agent_for_channel(platform, channel_id)
        if channel_agent is not None:
            return load_active(channel_agent.name)
    if user_id:
        user_agent = agent_store.get_agent_for_user(user_id)
        if user_agent is not None:
            return load_active(user_agent.name)
    default_agent = agent_store.get_default_agent()
    return None if default_agent is None else load_active(default_agent.name)


# MCP tools are registered as "{server_id}__{tool_name}"; the double underscore
# is the separator (single underscores are part of names).
_MCP_SEP = "__"


def _is_mcp_tool(name: str) -> bool:
    return _MCP_SEP in name


def filter_tool_schemas(
    schemas: list[ToolSchema],
    allowed_tools: list[str] | None,
    mcp_server_ids: list[str] | None,
) -> list[ToolSchema]:
    """Filter tool schemas by the agent's allowlist and MCP server whitelist.

    Two passes, both must pass for a tool to survive:

    1. ``allowed_tools``: when not ``None``, only tools matching one of the
       glob patterns (via ``check_tool_access``) are kept. ``None`` skips this pass.
    2. ``mcp_server_ids``: ``None`` skips this pass (no MCP restriction). An empty
       list drops every MCP tool (any name containing ``__``). A non-empty list
       keeps only MCP tools whose ``{server_id}__`` prefix is listed; non-MCP
       (built-in) tools are always kept.
    """
    result: list[ToolSchema] = []
    for schema in schemas:
        name = schema["function"]["name"]
        if allowed_tools is not None and not check_tool_access(name, allowed_tools):
            continue
        if mcp_server_ids is not None and _is_mcp_tool(name):
            server_id = name.split(_MCP_SEP, 1)[0]
            if server_id not in mcp_server_ids:
                continue
        result.append(schema)
    return result
