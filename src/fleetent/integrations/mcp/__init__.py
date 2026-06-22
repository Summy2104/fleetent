"""MCP integration public API."""

from fleetent.integrations.mcp.client import (
    McpServerConfig,
    aclose_all,
    call_tool,
    mcp_tool_identity,
    probe_server,
    project_schemas,
    project_tool_name,
    register_all,
    resolve_tool_name,
    set_tool_naming,
    unregister_server,
)

__all__ = [
    "McpServerConfig",
    "aclose_all",
    "call_tool",
    "mcp_tool_identity",
    "probe_server",
    "project_schemas",
    "project_tool_name",
    "register_all",
    "resolve_tool_name",
    "set_tool_naming",
    "unregister_server",
]
