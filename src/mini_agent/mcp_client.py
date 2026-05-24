"""MCP (Model Context Protocol) client for connecting to external tool servers.

Discovers tools from MCP-compatible HTTP servers and registers them into the
local tool_registry under namespaced names (server_id__tool_name).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_server_registry: dict[str, McpServerConfig] = {}


@dataclass
class McpServerConfig:
    id: str
    url: str
    auth_type: str = "none"  # "none" | "api_key" | "oauth2"
    api_key_env: str = ""


def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"


async def register_all(servers: list[McpServerConfig]) -> None:
    for server in servers:
        try:
            await _register_server(server)
        except Exception as exc:
            logger.warning("mcp_server_unavailable server_id=%s error=%s", server.id, exc)


async def _register_server(server: McpServerConfig) -> None:
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
        _register_tool(server, tool_name, tool_def)

    _server_registry[server.id] = server
    logger.info("mcp_server_registered server_id=%s tool_count=%d", server.id, len(tools))


def _register_tool(server: McpServerConfig, tool_name: str, tool_def: dict[str, Any]) -> None:
    import mini_agent.tool_registry as tr

    input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

    async def call(**kwargs: object) -> object:
        return await call_tool(server.id, tool_def["name"], kwargs)

    schema: tr.ToolSchema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_def.get("description", ""),
            "parameters": input_schema,
        },
    }

    tr._registry[tool_name] = (call, schema)


async def call_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> object:
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
    # Extract text content if MCP returned a content array
    if isinstance(result, dict):
        contents = result.get("content", [])
        if contents and isinstance(contents[0], dict):
            return contents[0].get("text", str(result))
    return str(result) if result is not None else ""
