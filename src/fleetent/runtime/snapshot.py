"""Runtime resolution of agent configuration into an executable snapshot.

Runtime resolution is file-sourced: the active snapshot and request routing come
from the self-contained ``agent.yaml`` index (``agent_config``) with zero database
access (file-driven-agent-config). Version-specific loaders
(``load_version``/``load_version_by_name``) stay DB-backed for the authoring/console
side. This module provides the pure tool-schema filter that enforces both the
per-agent ``allowed_tools`` allowlist and the MCP server whitelist.

It never imports the agent loop (one-way dependency: agent_loop -> agent_runtime).
"""

from dataclasses import dataclass
from typing import Any

from fleetent import agent_config, agent_store
from fleetent.agent_config import AgentFile, default_models
from fleetent.agent_store import AgentVersion
from fleetent.governance.agent_policy import check_tool_access
from fleetent.model import ModelPolicySnapshot
from fleetent.observability.structured_logging import get_logger

_logger = get_logger("runtime.snapshot")

ToolSchema = dict[str, Any]


@dataclass(frozen=True)
class GovernanceConfig:
    """Per-run governance the agent loop consumes, resolved from the agent's config.

    Defaults mirror the historical global ``Settings`` defaults so a snapshot built
    without an agent file (DB/authoring side) behaves exactly as before. File-sourced
    snapshots fill these from the agent's ``agent.yaml`` (see ``_governance_from_file``).
    The global budget dimension is intentionally absent (dropped in the consolidation).
    """

    # iteration / budget
    agent_max_turns: int = 50
    agent_max_consecutive_failures: int = 3
    agent_max_tokens: int = -1
    agent_grace_call_token_ratio: float = 0.05
    agent_grace_call_min_tokens: int = 512
    # cross-run layered budget — session/user/agent dims only (global dropped)
    agent_budget_session_turns: int = -1
    agent_budget_session_tokens: int = -1
    agent_budget_user_turns: int = -1
    agent_budget_user_tokens: int = -1
    agent_budget_agent_turns: int = -1
    agent_budget_agent_tokens: int = -1
    agent_budget_user_window: str = "weekly"
    agent_budget_agent_window: str = "weekly"
    # loop detection / guardrail / concurrency
    agent_loop_repeat_threshold: int = 3
    guardrail_repeat_threshold: int = 3
    agent_tool_parallel_max: int = 8
    loop_detect_ignore_arg_keys: tuple[str, ...] = ()
    # timeouts
    sub_agent_timeout_seconds: int = 300
    tool_default_timeout_seconds: float = 30.0
    # run-time input steering (C1)
    steering_mode: str = "steer"
    steering_max_pending: int = 8


def _governance_from_file(agent: AgentFile) -> GovernanceConfig:
    return GovernanceConfig(
        agent_max_turns=agent.agent_max_turns,
        agent_max_consecutive_failures=agent.agent_max_consecutive_failures,
        agent_max_tokens=agent.agent_max_tokens,
        agent_grace_call_token_ratio=agent.agent_grace_call_token_ratio,
        agent_grace_call_min_tokens=agent.agent_grace_call_min_tokens,
        agent_budget_session_turns=agent.agent_budget_session_turns,
        agent_budget_session_tokens=agent.agent_budget_session_tokens,
        agent_budget_user_turns=agent.agent_budget_user_turns,
        agent_budget_user_tokens=agent.agent_budget_user_tokens,
        agent_budget_agent_turns=agent.agent_budget_agent_turns,
        agent_budget_agent_tokens=agent.agent_budget_agent_tokens,
        agent_budget_user_window=agent.agent_budget_user_window,
        agent_budget_agent_window=agent.agent_budget_agent_window,
        agent_loop_repeat_threshold=agent.agent_loop_repeat_threshold,
        guardrail_repeat_threshold=agent.guardrail_repeat_threshold,
        agent_tool_parallel_max=agent.agent_tool_parallel_max,
        loop_detect_ignore_arg_keys=tuple(agent.loop_detect_ignore_arg_keys),
        sub_agent_timeout_seconds=agent.sub_agent_timeout_seconds,
        tool_default_timeout_seconds=agent.tool_default_timeout_seconds,
        steering_mode=agent.steering_mode,
        steering_max_pending=agent.steering_max_pending,
    )


@dataclass(frozen=True)
class AgentSnapshot:
    """Immutable, fully-resolved agent configuration the agent loop consumes."""

    # Identity is the agent name (string). Authoring DB rows still carry an int id,
    # rendered as its string form on the DB-backed version loaders.
    agent_id: str
    name: str
    version: int
    version_id: int
    system_prompt: str
    allowed_tools: list[str]
    skills_dir: str | None
    mcp_server_ids: list[str] | None
    model_policy: ModelPolicySnapshot
    memory_namespace: str
    governance: GovernanceConfig = GovernanceConfig()


def _snapshot_from_file(agent: AgentFile) -> AgentSnapshot:
    server_ids = [server.id for server in agent.mcp_servers]
    return AgentSnapshot(
        agent_id=agent.name,
        name=agent.name,
        version=agent.version,
        version_id=agent.version,
        system_prompt=agent.system_prompt,
        allowed_tools=agent.allowed_tools,
        skills_dir=agent.skills_dir,
        mcp_server_ids=server_ids or None,
        model_policy=ModelPolicySnapshot.from_agent(agent),
        memory_namespace=agent.memory_namespace,
        governance=_governance_from_file(agent),
    )


def _snapshot(name: str, version: AgentVersion) -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=str(version.agent_id),
        name=name,
        version=version.version,
        version_id=version.id,
        system_prompt=version.system_prompt,
        allowed_tools=version.allowed_tools,
        skills_dir=version.skills_dir,
        mcp_server_ids=version.mcp_server_ids,
        model_policy=ModelPolicySnapshot.from_models(agent_id=name, models=default_models()),
        memory_namespace=version.memory_namespace,
    )


def load_active(name: str) -> AgentSnapshot | None:
    """Resolve the agent's file-sourced snapshot, or ``None`` if absent. Zero DB."""
    agent = agent_config.current().get(name)
    if agent is None:
        _logger.warn("snapshot_not_found", agent=name)
        return None
    snap = _snapshot_from_file(agent)
    _logger.info("snapshot_loaded", agent=name, version_id=snap.version_id)
    return snap


def load_active_db(name: str) -> AgentSnapshot | None:
    """DB-backed active snapshot for the authoring/console side (NOT the runtime path)."""
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
    """Resolve the agent for a request from the file index: channel > user > default."""
    index = agent_config.current()
    name: str | None = None
    if platform and channel_id:
        name = index.agent_for_channel(platform, channel_id)
    if name is None and user_id:
        name = index.agent_for_user(user_id)
    if name is None:
        name = index.default_agent()
    return None if name is None else load_active(name)


# MCP tools are registered as "{server_id}__{tool_name}"; the double underscore
# is the separator (single underscores are part of names).
_MCP_SEP = "__"


def _is_mcp_tool(name: str) -> bool:
    return _MCP_SEP in name


def connector_scope(snapshot: AgentSnapshot) -> str:
    """The agent name used to resolve OAuth connectors for this snapshot."""
    return snapshot.agent_id


def resolve_mcp_servers(
    snapshot: AgentSnapshot, defaults: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Effective MCP set: the agent's inline file definitions overlaid on defaults. Zero DB."""
    merged: dict[str, dict[str, Any]] = {d["id"]: dict(d) for d in defaults}
    agent = agent_config.current().get(snapshot.name)
    if agent is not None:
        for server in agent.mcp_servers:
            merged[server.id] = server.model_dump()
    return sorted(merged.values(), key=lambda s: s["id"])


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
