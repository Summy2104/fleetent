"""Runtime resolution of agent configuration into an executable snapshot.

This module turns stored agent/version rows into the immutable ``AgentSnapshot``
the agent loop consumes, and provides the pure tool-schema filter that enforces
both the per-agent ``allowed_tools`` allowlist and the MCP server whitelist.

It never imports the agent loop (one-way dependency: agent_loop -> agent_runtime).
"""

from typing import Any

from fleetent.governance.agent_policy import check_tool_access

ToolSchema = dict[str, Any]

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
