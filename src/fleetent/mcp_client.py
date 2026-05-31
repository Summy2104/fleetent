"""MCP (Model Context Protocol) client for connecting to external tool servers.

Supports two transports:
  - http: standard MCP Streamable HTTP (initialize handshake, Accept negotiation for
    JSON/SSE responses, Mcp-Session-Id session management, monotonic request ids)
  - stdio: subprocess stdin/stdout (official MCP servers like filesystem, github)

Tools are registered into tool_registry under namespaced names: server_id__tool_name.
Stdio connections are kept alive via a module-level AsyncExitStack.
"""

from __future__ import annotations

import json
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
    transport: str = "http"  # "http" | "stdio"
    # HTTP fields
    url: str = ""
    auth_type: str = "none"  # "none" | "api_key" | "oauth2"
    api_key_env: str = ""
    # stdio fields
    command: str = ""  # e.g. "npx" or "python"
    args: list[str] = field(
        default_factory=list
    )  # e.g. ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env: dict[str, str] = field(default_factory=dict)  # extra env vars for the subprocess
    # Streamable HTTP runtime state (per-server, not module-level global)
    session_id: str | None = None  # assigned by server via Mcp-Session-Id on initialize
    _request_id: int = field(default=0, repr=False, compare=False)  # monotonic JSON-RPC id


def _next_request_id(server: McpServerConfig) -> int:
    """Return the next monotonic JSON-RPC request id for a server (per-server counter)."""
    server._request_id += 1
    return server._request_id


def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"


def _extract_jsonrpc_from_sse(body: str, request_id: int) -> dict[str, Any]:
    """Extract the JSON-RPC response matching request_id from an SSE response body.

    Parses Server-Sent Events: comment lines (starting with ':') are ignored,
    consecutive 'data:' lines within one event are concatenated, and a blank line
    terminates an event. Each event whose 'data' payload is a JSON-RPC object with
    the matching id is returned. Raises ValueError if no matching response is found.
    """
    data_lines: list[str] = []

    def try_match(lines: list[str]) -> dict[str, Any] | None:
        if not lines:
            return None
        payload = "\n".join(lines)
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if isinstance(obj, dict) and obj.get("id") == request_id:
            return obj
        return None

    for raw_line in body.splitlines():
        if raw_line == "":
            matched = try_match(data_lines)
            if matched is not None:
                return matched
            data_lines = []
            continue
        if raw_line.startswith(":"):
            continue
        field_name, _, value = raw_line.partition(":")
        if field_name != "data":
            continue
        data_lines.append(value[1:] if value.startswith(" ") else value)

    matched = try_match(data_lines)
    if matched is not None:
        return matched

    raise ValueError(f"No JSON-RPC response with id={request_id} found in SSE body")


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

    logger.info(
        "mcp_server_registered server_id=%s transport=stdio tool_count=%d", server.id, len(tools)
    )


PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "fleetent", "version": "1.0"}


def _base_headers(server: McpServerConfig) -> dict[str, str]:
    """Build request headers: Accept negotiation, optional Bearer auth, session id echo."""
    headers: dict[str, str] = {"Accept": "application/json, text/event-stream"}
    if server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    if server.session_id:
        headers["Mcp-Session-Id"] = server.session_id
    return headers


def _parse_jsonrpc_response(resp: Any, request_id: int) -> dict[str, Any]:
    """Parse a JSON or SSE response into the JSON-RPC object matching request_id."""
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return _extract_jsonrpc_from_sse(resp.text, request_id)
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected JSON-RPC response shape")
    return data


async def _post_jsonrpc(
    client: Any, server: McpServerConfig, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Send a JSON-RPC request and return the matched JSON-RPC response object."""
    request_id = _next_request_id(server)
    resp = await client.post(
        f"{server.url}/",
        json={"jsonrpc": "2.0", "method": method, "params": params, "id": request_id},
        headers=_base_headers(server),
    )
    resp.raise_for_status()
    obj = _parse_jsonrpc_response(resp, request_id)
    if "error" in obj:
        raise RuntimeError(f"MCP {method} error: {obj['error']}")
    return obj


async def _post_notification(client: Any, server: McpServerConfig, method: str) -> None:
    """Send a JSON-RPC notification (no id, no response expected); tolerate failures."""
    try:
        await client.post(
            f"{server.url}/",
            json={"jsonrpc": "2.0", "method": method},
            headers=_base_headers(server),
        )
    except Exception as exc:  # noqa: BLE001 — notification is best-effort
        logger.debug(
            "mcp_notification_failed server_id=%s method=%s error=%s", server.id, method, exc
        )


async def _register_http_server(server: McpServerConfig) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        request_id = _next_request_id(server)
        init_resp = await client.post(
            f"{server.url}/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
                "id": request_id,
            },
            headers=_base_headers(server),
        )
        init_resp.raise_for_status()
        session_id = init_resp.headers.get("Mcp-Session-Id")
        if session_id:
            server.session_id = session_id
        _parse_jsonrpc_response(init_resp, request_id)

        await _post_notification(client, server, "notifications/initialized")

        list_obj = await _post_jsonrpc(client, server, "tools/list", {})

    tools = list_obj.get("result", {}).get("tools", [])
    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def["name"])
        _register_tool_http(server, tool_name, tool_def)

    _server_registry[server.id] = server
    logger.info(
        "mcp_server_registered server_id=%s transport=http tool_count=%d", server.id, len(tools)
    )


def _register_tool_stdio(server: McpServerConfig, tool_name: str, tool_def: Any) -> None:
    import fleetent.tool_registry as tr

    input_schema = (
        tool_def.inputSchema
        if hasattr(tool_def, "inputSchema")
        else {"type": "object", "properties": {}}
    )

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
    import fleetent.tool_registry as tr

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

    async with httpx.AsyncClient(timeout=30.0) as client:
        obj = await _post_jsonrpc(
            client, server, "tools/call", {"name": tool_name, "arguments": args}
        )

    result = obj.get("result")
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
