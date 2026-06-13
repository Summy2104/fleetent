"""Backward-compatible shim for the renamed MCP server registry store."""

from fleetent.platform.connector_management.mcp_server_store import (
    _database,
    add_mcp_server,
    delete_mcp_server,
    edit_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    resolve_mcp_servers,
)

__all__ = [
    "_database",
    "add_mcp_server",
    "delete_mcp_server",
    "edit_mcp_server",
    "get_mcp_server",
    "list_mcp_servers",
    "resolve_mcp_servers",
]
