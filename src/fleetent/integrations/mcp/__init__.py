"""MCP integration public API."""

from fleetent.integrations.mcp.client import (
    McpServerConfig,
    call_tool,
    close,
    probe_server,
    register_all,
    unregister_server,
)

__all__ = [
    "McpServerConfig",
    "call_tool",
    "close",
    "probe_server",
    "register_all",
    "unregister_server",
]
