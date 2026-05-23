"""Tool registration and dispatch.

Tools are registered by importing modules that use the @tool decorator.
The agent loop calls get_schemas() for the API payload and dispatch() to execute.
"""

import inspect
import json
from collections.abc import Callable
from typing import Any

ToolSchema = dict[str, Any]

_registry: dict[str, tuple[Callable[..., str], ToolSchema]] = {}


def tool[F: Callable[..., str]](fn: F) -> F:
    """Register a function as a callable tool."""
    _registry[fn.__name__] = (fn, _build_schema(fn))
    return fn


def get_schemas() -> list[ToolSchema]:
    """Return OpenAI-format tool schemas for all registered tools."""
    return [schema for _, schema in _registry.values()]


def dispatch(
    name: str, arguments_json: str, allowed_tools: list[str] | None = None
) -> str:
    """Execute a registered tool by name with JSON-encoded arguments."""
    if allowed_tools is not None:
        from mini_agent.agent_policy import check_tool_access

        if not check_tool_access(name, allowed_tools):
            raise PermissionError(f"Tool '{name}' not permitted by agent policy")
    if name not in _registry:
        return f"unknown tool: {name}"
    fn, _ = _registry[name]
    kwargs: dict[str, Any] = json.loads(arguments_json)
    return fn(**kwargs)


def _build_schema(fn: Callable[..., str]) -> ToolSchema:
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
