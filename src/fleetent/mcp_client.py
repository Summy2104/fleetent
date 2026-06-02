"""Compatibility shim for MCP integrations."""

from fleetent.integrations.mcp.client import (
    McpServerConfig,
    _active_sessions,
    _call_http_tool,
    _call_stdio_tool,
    _make_tool_name,
    _register_http_server,
    _register_server,
    _register_stdio_server,
    _register_tool_http,
    _register_tool_stdio,
    _server_registry,
    call_tool,
    close,
    get_exit_stack,
    register_all,
)

__all__ = [
    "McpServerConfig",
    "_active_sessions",
    "_call_http_tool",
    "_call_stdio_tool",
    "_make_tool_name",
    "_register_http_server",
    "_register_server",
    "_register_stdio_server",
    "_register_tool_http",
    "_register_tool_stdio",
    "_server_registry",
    "call_tool",
    "close",
    "get_exit_stack",
    "register_all",
]
