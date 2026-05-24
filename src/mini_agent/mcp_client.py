"""MCP (Model Context Protocol) client for connecting to external tool servers.

Supports two transports:
  - http: JSON-RPC over HTTP (custom servers, legacy)
  - stdio: subprocess stdin/stdout (official MCP servers like filesystem, github)

Tools are registered into tool_registry under namespaced names: server_id__tool_name.
Stdio connections are kept alive via a module-level AsyncExitStack.
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_server_registry: dict[str, McpServerConfig] = {}
_active_sessions: dict[str, Any] = {}  # server_id -> mcp.ClientSession (stdio only)
_exit_stack: AsyncExitStack | None = None


@dataclass
class McpServerConfig:
    id: str
    transport: str = "http"         # "http" | "stdio"
    # HTTP fields
    url: str = ""
    auth_type: str = "none"         # "none" | "api_key" | "oauth2"
    api_key_env: str = ""
    # stdio fields
    command: str = ""               # e.g. "npx" or "python"
    args: list[str] = field(default_factory=list)  # e.g. ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env: dict[str, str] = field(default_factory=dict)  # extra env vars for the subprocess


def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"


async def get_exit_stack() -> AsyncExitStack:
    global _exit_stack
    if _exit_stack is None:
        _exit_stack = AsyncExitStack()
        await _exit_stack.__aenter__()
    return _exit_stack


async def close() -> None:
    """Close all stdio connections. Call on server shutdown."""
    global _exit_stack
    if _exit_stack is not None:
        await _exit_stack.__aexit__(None, None, None)
        _exit_stack = None
    _active_sessions.clear()


async def register_all(servers: list[McpServerConfig]) -> None:
    for server in servers:
        try:
            await _register_server(server)
        except Exception as exc:
            logger.warning("mcp_server_unavailable server_id=%s error=%s", server.id, exc)


async def _register_server(server: McpServerConfig) -> None:
    if server.transport == "stdio":
        await _register_stdio_server(server)
    else:
        await _register_http_server(server)


async def _register_stdio_server(server: McpServerConfig) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    merged_env = {**os.environ, **server.env} if server.env else None
    params = StdioServerParameters(
        command=server.command,
        args=server.args,
        env=merged_env,
    )

    stack = await get_exit_stack()
    read, write = await stack.enter_async_context(stdio_client(params))
    session: Any = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()

    _active_sessions[server.id] = session
    _server_registry[server.id] = server

    tools_result = await session.list_tools()
    tools = tools_result.tools
    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def.name)
        _register_tool_stdio(server, tool_name, tool_def)

    logger.info("mcp_server_registered server_id=%s transport=stdio tool_count=%d", server.id, len(tools))


async def _register_http_server(server: McpServerConfig) -> None:
    import httpx

    headers: dict[str, str] = {}
    if server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        resp = await client.post(
            f"{server.url}/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    tools = data.get("result", {}).get("tools", [])
    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def["name"])
        _register_tool_http(server, tool_name, tool_def)

    _server_registry[server.id] = server
    logger.info("mcp_server_registered server_id=%s transport=http tool_count=%d", server.id, len(tools))


def _register_tool_stdio(server: McpServerConfig, tool_name: str, tool_def: Any) -> None:
    import mini_agent.tool_registry as tr

    input_schema = tool_def.inputSchema if hasattr(tool_def, "inputSchema") else {"type": "object", "properties": {}}

    async def call(**kwargs: object) -> str:
        return await _call_stdio_tool(server.id, tool_def.name, dict(kwargs))

    schema: tr.ToolSchema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_def.description or "",
            "parameters": input_schema,
        },
    }
    tr._registry[tool_name] = (call, schema)


def _register_tool_http(server: McpServerConfig, tool_name: str, tool_def: dict[str, Any]) -> None:
    import mini_agent.tool_registry as tr

    input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

    async def call(**kwargs: object) -> str:
        return await _call_http_tool(server.id, tool_def["name"], dict(kwargs))

    schema: tr.ToolSchema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_def.get("description", ""),
            "parameters": input_schema,
        },
    }
    tr._registry[tool_name] = (call, schema)


async def _call_stdio_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    session = _active_sessions.get(server_id)
    if session is None:
        raise KeyError(f"No active stdio session for MCP server: {server_id}")
    result = await session.call_tool(tool_name, args)
    if result.content:
        return result.content[0].text
    return ""


async def _call_http_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    server = _server_registry.get(server_id)
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")

    import httpx

    headers: dict[str, str] = {}
    if server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        resp = await client.post(
            f"{server.url}/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
                "id": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    result = data.get("result")
    if isinstance(result, dict):
        contents = result.get("content", [])
        if contents and isinstance(contents[0], dict):
            return contents[0].get("text", str(result))
    return str(result) if result is not None else ""


# Keep call_tool as a public API for backward compatibility
async def call_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    server = _server_registry.get(server_id)
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    if server.transport == "stdio":
        return await _call_stdio_tool(server_id, tool_name, args)
    return await _call_http_tool(server_id, tool_name, args)
