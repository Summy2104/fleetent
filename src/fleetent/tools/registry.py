"""Tool registration and dispatch.

Tools are registered by importing modules that use the @tool decorator.
The agent loop calls get_schemas() for the API payload and dispatch() to execute.
"""

import inspect
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, cast, overload

logger = logging.getLogger(__name__)

ToolSchema = dict[str, Any]
ToolReturn = str | Coroutine[Any, Any, str]
ToolFn = Callable[..., ToolReturn]
# permission-gate D7: a risk level may be a callable evaluated at call time with
# (tool_args, tool_context) → "low" | "medium" | "high".
RiskFn = Callable[[dict[str, Any], Any], str]


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
    # Resolved workspace scope key (D0): the /exchange attribution key, mirroring the
    # /workspace mount (session_id under `session` scope, agent_name under `agent`). Set
    # by the loop from the sandbox manager's resolved scope; None = no attribution.
    scope_key: str | None = None
    # delivery-receipts (D2): the run id (for the delivery trace) and the run-level
    # delivery ledger — outbound tools append their DeliveryReceipt so the run can render
    # the fact trailer + audit. None ledger = no collection (e.g. non-loop direct calls).
    run_id: str | None = None
    delivery_ledger: list[Any] | None = None
    # Inbound sender/channel metadata (im_gateway.SessionContext) for whoami-style
    # tools; typed Any to avoid an im_gateway import cycle. None = unavailable.
    session_context: Any = None
    # Resolved execution identity (fleetent.identity.Principal) so tools that
    # persist ownership (e.g. schedule) record who is acting, not what the model
    # typed; typed Any to keep registry free of identity imports. None = unavailable.
    principal: Any = None
    # Live IM connectors keyed by platform (e.g. {"slack": client}) for tools that
    # send proactively (send_im_message). Empty when the run path has no IM gateway
    # (TUI / HTTP) — such tools must degrade with an explanatory result.
    outbound_connectors: dict[str, Any] = field(default_factory=dict)


_registry: dict[str, tuple[Callable[..., Any], ToolSchema]] = {}
_risk_levels: dict[str, "str | RiskFn"] = {}
# Per-tool timeout metadata parallel to _risk_levels (T2): name -> seconds. Absent
# means "use the global default". Like risk_level it never enters the LLM schema.
_timeouts: dict[str, float] = {}
# Global default tool timeout (seconds), module-level so tests/deploys can inject it.
DEFAULT_TOOL_TIMEOUT = 30.0
# Tools that cap their own output (T4 D5): name set. Such tools are exempt from the
# generic tool-result truncation (e.g. run_code, whose output SB6 already caps).
_self_truncating: set[str] = set()
# Connector metadata parallel to _risk_levels (D1): name -> (connector, scopes).
# Governance/dispatch-time runtime data; deliberately kept out of the LLM schema.
_connectors: dict[str, tuple[str, list[str]]] = {}
# Per-tool runtime availability predicate: name -> Callable[[], bool]. None means always
# available. get_schemas() evaluates each predicate on every call (no caching) so
# availability responds to runtime state changes (e.g. env vars set after startup).
_availability: dict[str, Callable[[], bool]] = {}


@overload
def tool[F: ToolFn](fn: F) -> F: ...


@overload
def tool(
    *,
    risk_level: "str | RiskFn" = "none",
    connector: str | None = None,
    scopes: list[str] | None = None,
    timeout: float | None = None,
    self_truncates: bool = False,
    availability: Callable[[], bool] | None = None,
) -> Callable[[ToolFn], ToolFn]: ...


def tool(
    fn: ToolFn | None = None,
    *,
    risk_level: "str | RiskFn" = "none",
    connector: str | None = None,
    scopes: list[str] | None = None,
    timeout: float | None = None,
    self_truncates: bool = False,
    availability: Callable[[], bool] | None = None,
) -> Any:
    """Register a function as a callable tool.

    Supports both `@tool` (bare) and `@tool(risk_level="medium")` forms.
    The risk_level is recorded so callers can route execution through the
    permission gate when needed. A `connector` (with optional `scopes`) declares
    that the tool needs an injected OAuth client at dispatch time; this metadata
    is stored parallel to risk_level and never enters the LLM-facing schema.
    """

    def _register(target: ToolFn) -> ToolFn:
        _registry[target.__name__] = (target, _build_schema(target))
        _risk_levels[target.__name__] = risk_level
        if connector is not None:
            _connectors[target.__name__] = (connector, scopes or [])
        if timeout is not None:
            _timeouts[target.__name__] = timeout
        if self_truncates:
            _self_truncating.add(target.__name__)
        if availability is not None:
            _availability[target.__name__] = availability
        return target

    if fn is not None:
        return _register(fn)
    return _register


def get_risk_level(name: str) -> str:
    """Return a tool's static risk level, defaulting to 'none'.

    For a tool whose risk is a callable (permission-gate D7), a conservative static
    view ('medium') is returned for context-free callers (e.g. trace logging) that
    cannot supply call args; the call-time disposition uses `evaluate_risk_level`.
    """
    value = _risk_levels.get(name, "none")
    if callable(value):
        return "medium"
    return value


def is_dynamic_risk(name: str) -> bool:
    """Whether a tool's risk is a call-time callable (permission-gate D7)."""
    return callable(_risk_levels.get(name))


def evaluate_risk_level(name: str, args: dict[str, Any], tool_context: Any) -> str:
    """Resolve a tool's risk at call time (permission-gate D7).

    A static string is returned as-is. A callable risk is evaluated with
    ``(args, tool_context)``; any exception fails closed to 'medium' so a buggy risk
    function can never silently downgrade a call below the approval threshold.
    """
    value = _risk_levels.get(name, "none")
    if not callable(value):
        return value
    try:
        return value(args, tool_context)
    except Exception:  # noqa: BLE001 — fail closed: a broken risk fn must not bypass the gate
        logger.warning("risk_callable_failed name=%s", name)
        return "medium"


def get_connector(name: str) -> tuple[str, list[str]] | None:
    """Return the (connector, scopes) declared for a tool, or None if undeclared."""
    return _connectors.get(name)


def get_timeout(name: str) -> float | None:
    """Return the per-tool timeout (seconds) declared via @tool(timeout=...), or None."""
    return _timeouts.get(name)


def get_effective_timeout(name: str, default: float | None = None) -> float:
    """Effective timeout: the per-tool override if declared, else the supplied global
    default (or the module constant when no default is passed)."""
    return _timeouts.get(name, DEFAULT_TOOL_TIMEOUT if default is None else default)


def is_self_truncating(name: str) -> bool:
    """Whether the tool caps its own output and is exempt from T4 truncation."""
    return name in _self_truncating


# Optional visibility predicate (MCP4 D4): given a tool name, return whether its
# schema should be exposed to the LLM. None = expose all (default; non-MCP / no
# degradation). Injected by mcp_client; an injection point, not mutable business
# state — the predicate reads live server health each call.
_schema_visibility_filter: Callable[[str], bool] | None = None


def set_schema_visibility_filter(fn: Callable[[str], bool] | None) -> None:
    """Install (or clear with None) the schema visibility predicate (MCP4 D4)."""
    global _schema_visibility_filter
    _schema_visibility_filter = fn


def get_schemas() -> list[ToolSchema]:
    """Return OpenAI-format tool schemas for registered tools that are currently available.

    Two filter layers applied on every call (no caching):
    - MCP visibility filter: hides tools when their MCP server is degraded.
    - Availability predicate: hides tools whose runtime condition is not met
      (e.g. missing env var, absent binary). Exceptions in the predicate are
      treated as unavailable and logged as warnings.
    """
    flt = _schema_visibility_filter
    result = []
    for name, (_fn, schema) in _registry.items():
        if flt is not None and not flt(name):
            continue
        avail_fn = _availability.get(name)
        if avail_fn is not None:
            try:
                if not avail_fn():
                    continue
            except Exception:
                logger.warning(
                    "availability check for tool %r raised; treating as unavailable", name
                )
                continue
        result.append(schema)
    return result


_SUB_AGENT_TOOL = "sub_agent"
_MCP_SEP = "__"

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
    mcp_server_ids: list[str] | None = None,
    mcp_scope: int | None = None,
) -> str | Coroutine[Any, Any, str]:
    """Execute a registered tool by name with JSON-encoded arguments.

    `cancel_token` and `tool_context` are injected out-of-band (not LLM-provided
    arguments) only for tools that opt in by declaring the matching parameter.

    For a tool declaring a `connector` (D3), the per-user credential is resolved via
    `connectors.get_credential(user_id, connector, scopes)`: a `Credential` injects its
    `client` as a hidden keyword-only argument; a `NeedsConsent` short-circuits to a
    consent prompt. The injected `client` never enters kwargs, the return, or a trace.

    For MCP tools (``server_id__tool``) ``mcp_server_ids`` is the agent's resolved server
    whitelist (out-of-scope ids rejected before any session is touched) and ``mcp_scope``
    routes the call through the scope-keyed MCP session rather than the global closure.
    """
    if is_sub_agent and name == _SUB_AGENT_TOOL:
        raise PermissionError("sub_agent tool is not available inside a sub-agent")
    from fleetent.governance.agent_policy import is_tool_visible

    if not is_tool_visible(name, allowed_tools):
        raise PermissionError(f"Tool '{name}' not permitted by agent policy")

    is_mcp = _MCP_SEP in name
    if is_mcp and mcp_server_ids is not None:
        server_id = name.split(_MCP_SEP, 1)[0]
        if server_id not in mcp_server_ids:
            raise PermissionError(f"MCP server '{server_id}' not in agent scope")

    kwargs: dict[str, Any] = (
        arguments_json if isinstance(arguments_json, dict) else json.loads(arguments_json)
    )
    # Agent-scoped MCP: route through the scope-keyed session, not the global closure.
    if is_mcp and mcp_scope is not None:
        from fleetent.integrations.mcp import client as mcp_client

        server_id, tool_name = name.split(_MCP_SEP, 1)
        # Thread /exchange attribution (D0): same scope_key the global path carries via
        # the wrapper's tool_context, plus session_id/user_id for the ledger audit columns.
        principal = getattr(tool_context, "principal", None)
        return mcp_client.call_tool(
            server_id,
            tool_name,
            kwargs,
            scope=mcp_scope,
            scope_key=getattr(tool_context, "scope_key", None),
            session_id=getattr(tool_context, "session_id", None),
            user_id=getattr(principal, "user_id", None),
        )

    if name not in _registry:
        return f"unknown tool: {name}"
    fn, _ = _registry[name]

    if cancel_token is not None and _accepts_cancel_token(fn):
        kwargs[_CANCEL_TOKEN_PARAM] = cancel_token
    if tool_context is not None and _accepts_tool_context(fn):
        kwargs[_TOOL_CONTEXT_PARAM] = tool_context

    connector_meta = get_connector(name)
    if connector_meta is None:
        return cast(ToolReturn, fn(**kwargs))

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
    return cast(ToolReturn, fn(**kwargs, client=cred.client))


def _build_schema(fn: Callable[..., Any]) -> ToolSchema:
    from fleetent.tools.schema_builder import build_schema

    return build_schema(fn)


def _py_type_to_json(ann: object) -> str:
    if ann is int:
        return "integer"
    if ann is float:
        return "number"
    if ann is bool:
        return "boolean"
    return "string"
