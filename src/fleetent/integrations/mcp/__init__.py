"""MCP integration public API."""

from fleetent.integrations.mcp.client import (
    McpServerConfig,
    aclose_all,
    call_tool,
    cleanup_orphan_stdio_hosts,
    mcp_tool_identity,
    probe_server,
    project_schemas,
    project_tool_name,
    register_all,
    resolve_tool_name,
    set_tool_naming,
    start_stdio_reaper,
    stop_stdio_reaper,
    unregister_server,
)

__all__ = [
    "McpServerConfig",
    "aclose_all",
    "call_tool",
    "cleanup_orphan_stdio_hosts",
    "mcp_tool_identity",
    "probe_server",
    "project_schemas",
    "project_tool_name",
    "register_all",
    "resolve_tool_name",
    "set_tool_naming",
    "start_stdio_reaper",
    "stop_stdio_reaper",
    "unregister_server",
]
