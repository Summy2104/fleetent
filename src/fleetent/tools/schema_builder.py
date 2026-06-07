"""Tool parameter schema builder with full Python type annotation support.

Supports: str/int/float/bool, list[T], Optional[T], T | None,
Literal[...], Annotated[T, description]. Out-of-band parameters
(cancel_token, tool_context, client) are always excluded.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any, get_args, get_origin

_OUT_OF_BAND_PARAMS = frozenset({"cancel_token", "tool_context", "client"})

ToolSchema = dict[str, Any]


def build_schema(fn: Callable[..., Any]) -> ToolSchema:
    """Build an OpenAI-format tool schema from a Python function's type annotations."""
    sig = inspect.signature(fn)
    description = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else fn.__name__
    # get_type_hints evaluates stringified annotations (from __future__ annotations)
    # include_extras=True preserves Annotated metadata
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in _OUT_OF_BAND_PARAMS:
            continue
        annotation = hints.get(param_name, param.annotation)
        prop = _resolve_annotation(annotation)
        properties[param_name] = prop
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


def _resolve_annotation(annotation: Any) -> dict[str, Any]:
    """Recursively resolve a type annotation to a JSON Schema property dict."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Annotated[T, "description", ...]
    if origin is typing.Annotated:
        inner = args[0]
        prop = _resolve_annotation(inner)
        # First string metadata becomes the description
        for meta in args[1:]:
            if isinstance(meta, str):
                prop["description"] = meta
                break
        return prop

    # Optional[T] desugars to Union[T, None] in Python < 3.10
    # T | None uses types.UnionType in Python 3.10+
    if origin is typing.Union or isinstance(annotation, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Optional[T] → resolve inner, strip from required at call site
            return _resolve_annotation(non_none[0])
        # Multi-union: fall back to string
        return {"type": "string"}

    # list[T]
    if origin is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _resolve_annotation(item_type)}

    # Literal["a", "b", ...]
    if origin is typing.Literal:
        all_int = all(isinstance(v, int) for v in args)
        return {"type": "integer" if all_int else "string", "enum": list(args)}

    # Primitive types
    return {"type": _py_type_to_json(annotation)}


def _py_type_to_json(ann: Any) -> str:
    if ann is int:
        return "integer"
    if ann is float:
        return "number"
    if ann is bool:
        return "boolean"
    return "string"
