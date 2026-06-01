"""Tool registration and dispatch.

Tools are registered by importing modules that use the @tool decorator.
The agent loop calls get_schemas() for the API payload and dispatch() to execute.
"""

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, overload

ToolSchema = dict[str, Any]


@dataclass
class ToolContext:
    """Execution-time context passed out-of-band to opt-in tools (SB3 D5).

    Carries the calling agent's identity, its feature switches, and the session
    id to tools that need them at execution time (SB2 scope acquire, SB5 env
    injection). It is NOT an enablement gate — the gate runs at schema-build time
    (agent_loop); a tool reaching dispatch is already authorised. SB2/SB5 reuse
    this channel rather than each re-threading the dispatch signature.
    """

    agent_name: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None


_registry: dict[str, tuple[Callable[..., Any], ToolSchema]] = {}
_risk_levels: dict[str, str] = {}
# Per-tool timeout metadata parallel to _risk_levels (T2): name -> seconds. Absent
# means "use the global default". Like risk_level it never enters the LLM schema.
_timeouts: dict[str, float] = {}
# Global default tool timeout (seconds), module-level so tests/deploys can inject it.
DEFAULT_TOOL_TIMEOUT = 30.0
# Connector metadata parallel to _risk_levels (D1): name -> (connector, scopes).
# Governance/dispatch-time runtime data; deliberately kept out of the LLM schema.
_connectors: dict[str, tuple[str, list[str]]] = {}


@overload
def tool[F: Callable[..., str]](fn: F) -> F: ...


@overload
def tool(
    *,
    risk_level: str = "none",
    connector: str | None = None,
    scopes: list[str] | None = None,
    timeout: float | None = None,
) -> Callable[[Callable[..., str]], Callable[..., str]]: ...


def tool(
    fn: Callable[..., str] | None = None,
    *,
    risk_level: str = "none",
    connector: str | None = None,
    scopes: list[str] | None = None,
    timeout: float | None = None,
) -> Any:
    """Register a function as a callable tool.

    Supports both `@tool` (bare) and `@tool(risk_level="medium")` forms.
    The risk_level is recorded so callers can route execution through the
    permission gate when needed. A `connector` (with optional `scopes`) declares
    that the tool needs an injected OAuth client at dispatch time; this metadata
    is stored parallel to risk_level and never enters the LLM-facing schema.
    """

    def _register(target: Callable[..., str]) -> Callable[..., str]:
        _registry[target.__name__] = (target, _build_schema(target))
        _risk_levels[target.__name__] = risk_level
        if connector is not None:
            _connectors[target.__name__] = (connector, scopes or [])
        if timeout is not None:
            _timeouts[target.__name__] = timeout
        return target

    if fn is not None:
        return _register(fn)
    return _register


def get_risk_level(name: str) -> str:
    """Return the registered risk level for a tool, defaulting to 'none'."""
    return _risk_levels.get(name, "none")


def get_connector(name: str) -> tuple[str, list[str]] | None:
    """Return the (connector, scopes) declared for a tool, or None if undeclared."""
    return _connectors.get(name)


def get_timeout(name: str) -> float | None:
    """Return the per-tool timeout (seconds) declared via @tool(timeout=...), or None."""
    return _timeouts.get(name)


def get_effective_timeout(name: str) -> float:
    """Effective timeout: the per-tool override if declared, else the global default."""
    return _timeouts.get(name, DEFAULT_TOOL_TIMEOUT)


def get_schemas() -> list[ToolSchema]:
    """Return OpenAI-format tool schemas for all registered tools."""
    return [schema for _, schema in _registry.values()]


_SUB_AGENT_TOOL = "sub_agent"

# Runtime out-of-band parameter (AR19 D3): a tool opts into receiving the cancel
# token by declaring a parameter with this name. `dispatch` injects the token
# only for such tools; `_build_schema` excludes it from the LLM-facing schema so
# it is never surfaced as a model-provided argument.
_CANCEL_TOKEN_PARAM = "cancel_token"

# Like the cancel token: an out-of-band parameter a tool opts into by declaring
# `tool_context`. Injected at dispatch time, excluded from the LLM-facing schema.
_TOOL_CONTEXT_PARAM = "tool_context"

# The hidden connector client (D3/D4): a connector tool opts into receiving its
# authorized client by declaring a keyword-only `client` parameter. dispatch
# injects it; it must never appear in the LLM schema (else the model could
# supply or tamper with the credential).
_CLIENT_PARAM = "client"

# Out-of-band parameter names never surfaced in the LLM schema.
_OUT_OF_BAND_PARAMS = frozenset({_CANCEL_TOKEN_PARAM, _TOOL_CONTEXT_PARAM, _CLIENT_PARAM})


def _accepts_cancel_token(fn: Callable[..., Any]) -> bool:
    """True if `fn` declares the out-of-band cancel-token parameter (opt-in)."""
    return _CANCEL_TOKEN_PARAM in inspect.signature(fn).parameters


def _accepts_tool_context(fn: Callable[..., Any]) -> bool:
    """True if `fn` declares the out-of-band tool-context parameter (opt-in)."""
    return _TOOL_CONTEXT_PARAM in inspect.signature(fn).parameters


def dispatch(
    name: str,
    arguments_json: str | dict[str, Any],
    allowed_tools: list[str] | None = None,
    is_sub_agent: bool = False,
    cancel_token: Any = None,
    tool_context: ToolContext | None = None,
    user_id: str | None = None,
) -> str:
    """Execute a registered tool by name with JSON-encoded arguments.

    `cancel_token` and `tool_context` are injected out-of-band (not LLM-provided
    arguments) only for tools that opt in by declaring the matching parameter; for
    all other tools the call is byte-identical to one made without them.

    For a tool declaring a `connector` (D3), the per-user credential is resolved
    via `connectors.get_credential(user_id, connector, scopes)`: a `Credential`
    injects its `client` as a hidden keyword-only argument; a `NeedsConsent`
    short-circuits and returns a consent prompt without executing the tool. The
    injected `client` never enters `kwargs`, the return value, or any trace.
    """
    if is_sub_agent and name == _SUB_AGENT_TOOL:
        raise PermissionError("sub_agent tool is not available inside a sub-agent")
    if allowed_tools is not None:
        from fleetent.agent_policy import check_tool_access

        if not check_tool_access(name, allowed_tools):
            raise PermissionError(f"Tool '{name}' not permitted by agent policy")
    if name not in _registry:
        return f"unknown tool: {name}"
    fn, _ = _registry[name]
    kwargs: dict[str, Any] = (
        arguments_json if isinstance(arguments_json, dict) else json.loads(arguments_json)
    )
    if cancel_token is not None and _accepts_cancel_token(fn):
        kwargs[_CANCEL_TOKEN_PARAM] = cancel_token
    if tool_context is not None and _accepts_tool_context(fn):
        kwargs[_TOOL_CONTEXT_PARAM] = tool_context

    connector_meta = get_connector(name)
    if connector_meta is None:
        result = fn(**kwargs)
        return result  # type: ignore[no-any-return]

    from fleetent import connectors

    connector, scopes = connector_meta
    cred = connectors.get_credential(user_id, connector, scopes)
    if isinstance(cred, connectors.NeedsConsent):
        return (
            f"connector '{cred.connector}' requires authorization before this tool can run. "
            f"Ask the user to grant access here: {cred.consent_url}"
        )
    # Inject the client out-of-band (keyword-only, excluded from the schema); it
    # is never written back into kwargs, so it cannot reach the return value or trace.
    result = fn(**kwargs, client=cred.client)
    return result  # type: ignore[no-any-return]


def _build_schema(fn: Callable[..., Any]) -> ToolSchema:
    sig = inspect.signature(fn)
    description = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else fn.__name__
    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        # Exclude out-of-band params (cancel_token AR19 D3, tool_context SB3 D5):
        # injected at dispatch time, not provided by the LLM, so they must not
        # appear in the parameter schema (else they'd be required string fields).
        if param_name in _OUT_OF_BAND_PARAMS:
            continue
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
