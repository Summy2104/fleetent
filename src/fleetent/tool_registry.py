"""Tool registration and dispatch.

Tools are registered by importing modules that use the @tool decorator.
The agent loop calls get_schemas() for the API payload and dispatch() to execute.
"""

import inspect
import json
from collections.abc import Callable, Coroutine
from typing import Any, cast, overload

ToolSchema = dict[str, Any]

_registry: dict[str, tuple[Callable[..., Any], ToolSchema]] = {}
_risk_levels: dict[str, str] = {}


ToolFunc = Callable[..., str | Coroutine[Any, Any, str]]


@overload
def tool[F: ToolFunc](fn: F) -> F: ...


@overload
def tool(*, risk_level: str = "none") -> Callable[[ToolFunc], ToolFunc]: ...


def tool(
    fn: ToolFunc | None = None,
    *,
    risk_level: str = "none",
) -> Any:
    """Register a function as a callable tool.

    Supports both `@tool` (bare) and `@tool(risk_level="medium")` forms.
    The risk_level is recorded so callers can route execution through the
    permission gate when needed.
    """

    def _register(target: ToolFunc) -> ToolFunc:
        _registry[target.__name__] = (target, _build_schema(target))
        _risk_levels[target.__name__] = risk_level
        return target

    if fn is not None:
        return _register(fn)
    return _register


def get_risk_level(name: str) -> str:
    """Return the registered risk level for a tool, defaulting to 'none'."""
    return _risk_levels.get(name, "none")


def get_schemas() -> list[ToolSchema]:
    """Return OpenAI-format tool schemas for all registered tools."""
    return [schema for _, schema in _registry.values()]


_SUB_AGENT_TOOL = "sub_agent"
_MCP_SEP = "__"


def dispatch(
    name: str,
    arguments_json: str | dict[str, Any],
    allowed_tools: list[str] | None = None,
    is_sub_agent: bool = False,
    mcp_server_ids: list[str] | None = None,
    mcp_scope: int | None = None,
) -> str | Coroutine[Any, Any, str]:
    """Execute a registered tool by name with JSON-encoded arguments.

    For MCP tools (``server_id__tool``) ``mcp_server_ids`` is the agent's resolved
    server whitelist and ``mcp_scope`` its credential scope (agent_id). A tool whose
    ``server_id`` is outside that whitelist is rejected before any session is touched,
    so a global session can never satisfy an out-of-scope call. When ``mcp_scope`` is
    set, the call is routed through the scope-keyed MCP session/credential rather than
    the globally-registered closure.
    """
    if is_sub_agent and name == _SUB_AGENT_TOOL:
        raise PermissionError("sub_agent tool is not available inside a sub-agent")
    if allowed_tools is not None:
        from fleetent.governance.agent_policy import check_tool_access

        if not check_tool_access(name, allowed_tools):
            raise PermissionError(f"Tool '{name}' not permitted by agent policy")

    is_mcp = _MCP_SEP in name
    if is_mcp and mcp_server_ids is not None:
        server_id = name.split(_MCP_SEP, 1)[0]
        if server_id not in mcp_server_ids:
            raise PermissionError(f"MCP server '{server_id}' not in agent scope")

    kwargs: dict[str, Any] = (
        arguments_json if isinstance(arguments_json, dict) else json.loads(arguments_json)
    )

    if is_mcp and mcp_scope is not None:
        from fleetent.integrations.mcp import client as mcp_client

        server_id, tool_name = name.split(_MCP_SEP, 1)
        return mcp_client.call_tool(server_id, tool_name, kwargs, scope=mcp_scope)

    if name not in _registry:
        return f"unknown tool: {name}"
    fn, _ = _registry[name]
    return cast(str | Coroutine[Any, Any, str], fn(**kwargs))


def _build_schema(fn: Callable[..., Any]) -> ToolSchema:
    sig = inspect.signature(fn)
    description = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else fn.__name__
    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        properties[param_name] = {"type": _py_type_to_json(param.annotation)}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _py_type_to_json(ann: object) -> str:
    if ann is int:
        return "integer"
    if ann is float:
        return "number"
    if ann is bool:
        return "boolean"
    return "string"
