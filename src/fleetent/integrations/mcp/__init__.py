"""MCP integration public API."""

from fleetent.integrations.mcp.client import (
    McpServerConfig,
    call_tool,
    close,
    register_all,
    start_health_monitor,
    stop_health_monitor,
)

__all__ = [
    "McpServerConfig",
    "call_tool",
    "close",
    "register_all",
    "start_health_monitor",
    "stop_health_monitor",
]
