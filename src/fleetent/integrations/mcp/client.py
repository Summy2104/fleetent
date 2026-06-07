"""MCP (Model Context Protocol) client for connecting to external tool servers.

Supports two transports:
  - http: standard MCP Streamable HTTP (initialize handshake, Accept negotiation for
    JSON/SSE responses, Mcp-Session-Id session management, monotonic request ids)
  - stdio: subprocess stdin/stdout (official MCP servers like filesystem, github)

Tools are registered into tool_registry under namespaced names: server_id__tool_name.
Stdio connections are kept alive via a module-level AsyncExitStack.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fleetent.runtime.error_classifier import ErrorClassification

logger = logging.getLogger(__name__)

_server_registry: dict[tuple[int | None, str], McpServerConfig] = {}
# Ids of strict-mode servers that failed to register at startup (MCP4 D5): not in
# _server_registry (never registered) yet still strict-unavailable for the query.
_failed_strict_servers: set[str] = set()
_active_sessions: dict[tuple[int | None, str], Any] = {}  # (scope, server_id) -> stdio session
_exit_stack: AsyncExitStack | None = None

# --- MCP3: connection health & reconnect tunables (injectable defaults) ----
# Reconnect backoff (D4): 1s -> 2s -> 4s -> ... capped at 60s; after this many
# consecutive failed reconnects a server is marked permanently unavailable.
# These are module-level *constants* (read-only defaults), not mutable per-server
# state — per-server state (health, attempt count) lives on the server instance.
_PROBE_INTERVAL = 30.0  # seconds between background health probes (D3)
_BACKOFF_BASE = 1.0  # seconds; first reconnect delay (D4)
_BACKOFF_CAP = 60.0  # seconds; reconnect backoff ceiling (D4)
_RECONNECT_MAX_ATTEMPTS = 5  # consecutive failures -> unavailable (D4)
_MAX_TOOL_PAGES = 100  # tools/list pagination safety cap: stop following nextCursor past this

_UNAVAILABLE_RESULT_PREFIX = "MCP server"  # tool result text on degraded/unavailable (D5)

# Single background health-monitor task (server-process lifespan only, D6).
_health_monitor_task: asyncio.Task[None] | None = None


class HealthState(StrEnum):
    """Connection health of an MCP server (D2). str-valued for trace output."""

    healthy = "healthy"  # connection live, tools callable
    degraded = "degraded"  # disconnect detected, reconnecting in background
    unavailable = "unavailable"  # reconnect threshold hit; auto-reconnect stopped


# Refresh slightly before the server-stated expiry to avoid a "valid at check, expired at
# the server" race (D4). Conservative TTL used when the token response omits expires_in.
_OAUTH_EXPIRY_SAFETY_MARGIN = 30.0  # seconds
_OAUTH_DEFAULT_TTL = 300.0  # seconds, when expires_in is missing


def _now() -> float:
    """Current wall-clock time source for token-expiry decisions (D4: injectable).

    Indirected through this function so tests can monkeypatch a deterministic clock
    instead of relying on real time.time().
    """
    return time.time()


@dataclass
class OAuthToken:
    access_token: str
    expires_at: float  # absolute wall-clock time (seconds), per _now()
    refresh_token: str | None = None


class OAuthAuthUnavailableError(RuntimeError):
    """Raised when an oauth2 server's credentials/authorization are unusable (D5).

    Signals a sticky "authentication unavailable" condition (token endpoint returned
    401 / invalid_client / invalid_grant): retrying with the same credentials is futile,
    so callers stop and surface re-authorization guidance.
    """


class _InMemoryTokenStore:
    """Per-server in-memory OAuth token cache (D3).

    Each oauth2 server instance holds its own store, so there is no module-level mutable
    token table. The keying by server_id is internal bookkeeping within one store.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, OAuthToken] = {}

    def get(self, server_id: str) -> OAuthToken | None:
        return self._tokens.get(server_id)

    def set(
        self,
        server_id: str,
        *,
        access_token: str,
        expires_at: float,
        refresh_token: str | None,
    ) -> None:
        self._tokens[server_id] = OAuthToken(
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    def clear(self, server_id: str) -> None:
        self._tokens.pop(server_id, None)


def _default_token_store() -> _InMemoryTokenStore:
    return _InMemoryTokenStore()


@dataclass
class McpServerConfig:
    id: str
    transport: str = "http"  # "http" | "stdio"
    # Degradation policy when this server is unavailable (MCP4): "degrade" (drop
    # its tools, others continue), "strict" (fail bound agents loudly), "silent"
    # (drop + log only). Invalid values fall back to "degrade" in __post_init__.
    degrade_mode: str = "degrade"
    # HTTP fields
    url: str = ""
    auth_type: str = "none"  # "none" | "api_key" | "oauth2"
    api_key_env: str = ""
    # Extra HTTP headers sent verbatim on every request (e.g. a server-specific
    # X-API-Key that does not fit the Authorization: Bearer model).
    headers: dict[str, str] = field(default_factory=dict)
    # OAuth2 fields (auth_type == "oauth2"); token_url points at a customer-internal,
    # self-hosted authorization server — never a cloud identity service.
    token_url: str = ""
    client_id: str = ""
    client_secret_env: str = ""  # env var holding the client secret (not stored in plaintext)
    scope: str = ""
    # stdio fields
    command: str = ""  # e.g. "npx" or "python"
    args: list[str] = field(
        default_factory=list
    )  # e.g. ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env: dict[str, str] = field(default_factory=dict)  # extra env vars for the subprocess
    # Per-server HTTP timeouts in seconds: connect/discovery/probe/token vs tool call.
    connect_timeout: float = 10.0
    call_timeout: float = 30.0
    # Streamable HTTP runtime state (per-server, not module-level global)
    session_id: str | None = None  # assigned by server via Mcp-Session-Id on initialize
    # Negotiated protocol version + server-advertised capabilities, captured at initialize
    # (per-server runtime state, never module-level global; capabilities gate later features).
    protocol_version: str | None = field(default=None, repr=False, compare=False)
    capabilities: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    _request_id: int = field(default=0, repr=False, compare=False)  # monotonic JSON-RPC id
    # OAuth2 runtime state, held per-server instance (D3/D5/D9: never module-level global)
    _token_store: _InMemoryTokenStore = field(
        default_factory=_default_token_store, repr=False, compare=False
    )
    _refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    _auth_unavailable: bool = field(default=False, repr=False, compare=False)
    # MCP3 connection-health state, held per-server (D2: never module-level global).
    _health: HealthState = field(default=HealthState.healthy, repr=False, compare=False)
    _reconnect_attempts: int = field(default=0, repr=False, compare=False)
    _reconnect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    # Coalesces tools/list_changed-driven refreshes for this stdio server (mcp-dynamic-tools).
    _list_refresh_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, repr=False, compare=False
    )
    # Agent-scope key dimension (next<-main integration): registries/sessions are keyed
    # by (agent_scope, id) so the same server id can carry distinct credentials/sessions
    # per agent. None = the global (startup) scope. Distinct from the oauth `scope` str.
    _agent_scope: int | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_degrade_mode(self)


_VALID_DEGRADE_MODES = ("degrade", "strict", "silent")


def _validate_degrade_mode(server: McpServerConfig) -> None:
    """Fall back an invalid degrade_mode to 'degrade' (logged, never silently)."""
    if server.degrade_mode not in _VALID_DEGRADE_MODES:
        logger.warning(
            "mcp_invalid_degrade_mode server_id=%s value=%r falling_back=degrade",
            server.id,
            server.degrade_mode,
        )
        server.degrade_mode = "degrade"


def is_server_available(server: McpServerConfig) -> bool:
    """Whether a server's tools may be exposed now: connection healthy AND, for
    oauth2, auth available (MCP4 D1). Pure read of per-server state, no side effects."""
    return server._health is HealthState.healthy and not (
        server.auth_type == "oauth2" and server._auth_unavailable
    )


def _schema_visibility(tool_name: str) -> bool:
    """Visibility predicate for tool_registry (MCP4 D2/D4): hide tools of an
    unavailable MCP server. Non-MCP tools and unknown servers are always visible."""
    if "__" not in tool_name:
        return True
    server_id = tool_name.split("__", 1)[0]
    # Global-schema visibility concerns globally-registered (scope=None) servers; the
    # agent-scoped tools are routed via call_tool(scope), not the global schema.
    server = _server_registry.get((None, server_id))
    if server is None:
        return True
    return is_server_available(server)


def install_schema_filter() -> None:
    """Wire the MCP visibility predicate into tool_registry (MCP4 D4)."""
    from fleetent.tools import registry as tool_registry

    tool_registry.set_schema_visibility_filter(_schema_visibility)


def unavailable_strict_server_ids() -> set[str]:
    """Ids of strict-mode servers currently unavailable — registered-but-unavailable
    plus startup-failed strict servers (MCP4 D3/D5). agent_loop intersects these with
    an agent's allowed_tools `{id}__*` namespace to decide a strict failure stop."""
    registered = {
        sid
        for (_scope, sid), s in _server_registry.items()
        if s.degrade_mode == "strict" and not is_server_available(s)
    }
    return registered | set(_failed_strict_servers)


def unavailable_servers() -> list[tuple[str, str]]:
    """All currently-unavailable servers as (server_id, degrade_mode) (MCP4).

    Registered-but-unavailable servers report their configured mode; startup-failed
    strict servers (never registered) report `strict`. Lets agent_loop decide per
    mode: strict → stop the bound agent, degrade/silent → log (level by mode)."""
    out = [
        (sid, s.degrade_mode)
        for (_scope, sid), s in _server_registry.items()
        if not is_server_available(s)
    ]
    registered_ids = {sid for (_scope, sid) in _server_registry}
    out.extend((sid, "strict") for sid in _failed_strict_servers if sid not in registered_ids)
    return out


def _next_request_id(server: McpServerConfig) -> int:
    """Return the next monotonic JSON-RPC request id for a server (per-server counter)."""
    server._request_id += 1
    return server._request_id


def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"


# === MCP3: connection health & reconnect ===================================


def get_health(server: McpServerConfig) -> HealthState:
    """Current connection health of a server (D2)."""
    return server._health


def set_health(server: McpServerConfig, state: HealthState) -> None:
    """Set a server's connection health (D2: per-server, injectable for tests)."""
    server._health = state


def reset_health(server: McpServerConfig) -> None:
    """Reset a server to healthy with a zeroed reconnect counter (D2)."""
    server._health = HealthState.healthy
    server._reconnect_attempts = 0


def _is_disconnect_error(exc: BaseException) -> bool:
    """Whether an exception is a connection-level disconnect (D1/D7).

    Connection-level means the transport itself failed: the HTTP endpoint is
    unreachable / the read stream broke, or a stdio subprocess died. This is
    distinct from a session-level 404 (MCP2) — an ``HTTPStatusError`` carries a
    response and is explicitly NOT treated as a disconnect here, so 404 session
    expiry never enters the MCP3 reconnect/degrade path.
    """
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        return False
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError)):
        return True
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    # stdio: a dead subprocess / closed pipe surfaces as a connection/OS-level error.
    return isinstance(exc, (ConnectionError, BrokenPipeError, EOFError, OSError))


def _disconnect_classification() -> ErrorClassification:
    """Read AR5's mcp_disconnect classification directly (D1).

    The disconnect→category decision is mcp_client's own domain knowledge; we then
    consume AR5's read-only ``should_retry`` flag straight from CLASSIFICATION_TABLE.
    We deliberately do NOT call ``error_classifier.classify()`` — it only recognizes
    ``APIStatusError`` and would return ``unknown`` for a disconnect exception.
    """
    from fleetent.runtime.error_classifier import CLASSIFICATION_TABLE, ErrorCategory

    return CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect]


def _unavailable_result(server_id: str) -> str:
    """Tool-call result text when a server is degraded/unavailable (D5)."""
    return (
        f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' is temporarily unavailable "
        f"(connection lost; reconnecting in the background)."
    )


def _handle_disconnect(server: McpServerConfig) -> str:
    """Map a caught disconnect to AR5 mcp_disconnect and degrade + schedule reconnect (D1).

    Reads the mcp_disconnect classification's ``should_retry``: when true (it is, per
    AR5), transitions the server to ``degraded`` and kicks off a background reconnect.
    Returns the user-facing unavailable text (D5).
    """
    classification = _disconnect_classification()
    if classification.should_retry and server._health is HealthState.healthy:
        set_health(server, HealthState.degraded)
        _schedule_reconnect(server)
    return _unavailable_result(server.id)


def _backoff_delay(
    attempt: int, *, base: float = _BACKOFF_BASE, cap: float = _BACKOFF_CAP
) -> float:
    """Exponential backoff delay for reconnect attempt ``attempt`` (0-based), capped (D4)."""
    return min(base * (2.0**attempt), cap)


async def _attempt_reconnect(server: McpServerConfig) -> None:
    """One reconnect attempt (D4): re-register on success, count failures, cap to unavailable.

    Idempotent / deduplicated via the server's reconnect lock so concurrent triggers
    coalesce into a single in-flight reconnect.
    """
    if server._reconnect_lock.locked():
        return
    async with server._reconnect_lock:
        try:
            await _register_server(server)
        except Exception as exc:  # noqa: BLE001 — reconnect failure is expected; counted below
            server._reconnect_attempts += 1
            if server._reconnect_attempts >= _RECONNECT_MAX_ATTEMPTS:
                set_health(server, HealthState.unavailable)
                logger.warning(
                    "mcp_server_unavailable server_id=%s attempts=%d error=%s",
                    server.id,
                    server._reconnect_attempts,
                    exc,
                )
            else:
                logger.info(
                    "mcp_reconnect_failed server_id=%s attempt=%d error=%s",
                    server.id,
                    server._reconnect_attempts,
                    exc,
                )
            return
        reset_health(server)
        logger.info("mcp_server_reconnected server_id=%s", server.id)


async def _reconnect_with_backoff(server: McpServerConfig) -> None:
    """Background reconnect loop with exponential backoff until healthy or unavailable (D4)."""
    while server._health is HealthState.degraded:
        delay = _backoff_delay(server._reconnect_attempts)
        await asyncio.sleep(delay)
        await _attempt_reconnect(server)


def _schedule_reconnect(server: McpServerConfig) -> None:
    """Kick off a background reconnect loop for a degraded server (D4/D6).

    Fire-and-forget asyncio task; dedup is enforced inside ``_attempt_reconnect`` via
    the per-server reconnect lock so concurrent callers do not stack reconnects.
    """
    asyncio.create_task(_reconnect_with_backoff(server))


async def reconnect(server_id: str) -> None:
    """Manual reconnect entry point (D4): retry an unavailable/degraded server once.

    Clears the failure count so a previously ``unavailable`` server gets a fresh attempt.
    Targets the global (scope=None) registration.
    """
    server = _server_registry.get((None, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    server._reconnect_attempts = 0
    set_health(server, HealthState.degraded)
    await _attempt_reconnect(server)


async def _probe_once(server: McpServerConfig) -> None:
    """Probe one server's liveness (D3): HTTP light request / stdio session check.

    Auto-probe skips ``unavailable`` servers (they need a manual reconnect). On a
    detected disconnect the server is degraded and a background reconnect scheduled.
    """
    if server._health is not HealthState.healthy:
        return  # degraded already reconnecting; unavailable needs manual reconnect
    if server.transport == "stdio":
        if _active_sessions.get((server._agent_scope, server.id)) is None:
            set_health(server, HealthState.degraded)
            _schedule_reconnect(server)
        return

    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=server.connect_timeout, follow_redirects=True
        ) as client:
            await _post_jsonrpc(client, server, "tools/list", {})
    except Exception as exc:  # noqa: BLE001 — probe maps disconnects; other errors logged
        if _is_disconnect_error(exc):
            set_health(server, HealthState.degraded)
            _schedule_reconnect(server)
        else:
            logger.debug("mcp_probe_non_disconnect server_id=%s error=%s", server.id, exc)


async def _health_monitor_loop(interval: float) -> None:
    """Periodically probe all registered servers (D3/D6: bare asyncio, no cron)."""
    while True:
        await asyncio.sleep(interval)
        for server in list(_server_registry.values()):
            await _probe_once(server)


def start_health_monitor(*, interval: float = _PROBE_INTERVAL) -> asyncio.Task[None]:
    """Start the background health-monitor task (D6: server lifespan only, not CLI).

    Implemented as a bare ``asyncio.create_task`` loop — deliberately NOT routed through
    cron_scheduler/APScheduler (D6: decoupled from the deferred user-level scheduler).
    """
    global _health_monitor_task
    if _health_monitor_task is not None and not _health_monitor_task.done():
        return _health_monitor_task
    _health_monitor_task = asyncio.create_task(_health_monitor_loop(interval))
    return _health_monitor_task


async def stop_health_monitor() -> None:
    """Cancel the background health-monitor task, leaving no residual task (D6)."""
    global _health_monitor_task
    if _health_monitor_task is None:
        return
    _health_monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await _health_monitor_task
    _health_monitor_task = None


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
    """Close all connections on shutdown.

    Closes stdio connections and proactively releases active Streamable HTTP sessions
    by sending a DELETE (with the Mcp-Session-Id header) to each http server's session
    endpoint, then clears its local session id. The DELETE is best-effort: failures are
    logged at debug and never block shutdown.
    """
    global _exit_stack
    await stop_health_monitor()  # MCP3: cancel background prober, leave no residual task (D6)
    await _close_http_sessions()
    if _exit_stack is not None:
        await _exit_stack.__aexit__(None, None, None)
        _exit_stack = None
    _active_sessions.clear()


async def _close_http_sessions() -> None:
    """Send DELETE for each active HTTP session (best-effort), then expire it locally."""
    active = [
        s for s in _server_registry.values() if s.transport == "http" and s.session_id is not None
    ]
    if not active:
        return

    import httpx

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for server in active:
            try:
                bearer = await _bearer_for(server)
                await client.delete(f"{server.url}/", headers=_base_headers(server, bearer=bearer))
            except Exception as exc:  # noqa: BLE001 — DELETE is best-effort on shutdown
                logger.debug("mcp_session_delete_failed server_id=%s error=%s", server.id, exc)
            finally:
                _expire_session(server)


async def register_all(servers: list[McpServerConfig], scope: int | None = None) -> None:
    _failed_strict_servers.clear()  # recompute startup-failed strict set each registration
    for server in servers:
        try:
            await _register_server(server, scope)
        except Exception as exc:
            # Startup failure = unregistered = tools never visible (MCP4 D5); platform
            # start is NOT blocked. A strict server's failure is tracked so bound
            # agents can be stopped with a clear error (unavailable_strict_server_ids).
            logger.warning("mcp_server_unavailable server_id=%s error=%s", server.id, exc)
            if server.degrade_mode == "strict":
                _failed_strict_servers.add(server.id)
    # MCP4 D4: expose the visibility filter so unavailable servers' tools drop out
    # of get_schemas() (recovery re-exposes them, no re-registration).
    install_schema_filter()


async def _register_server(server: McpServerConfig, scope: int | None = None) -> None:
    server._agent_scope = scope
    if server.auth_type == "oauth2":
        _clear_oauth_auth_state(server)  # (re-)registration clears sticky auth state (D5)
    if server.transport == "stdio":
        await _register_stdio_server(server, scope)
    else:
        await _register_http_server(server, scope)


# stdio subprocess environment isolation (mcp-stdio-isolation): never inherit the full
# platform environment — only a vetted whitelist of host vars plus the server's own env.
_SAFE_ENV_KEYS_POSIX = (
    "HOME",
    "LOGNAME",
    "PATH",
    "SHELL",
    "TERM",
    "USER",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TZ",
)
_SAFE_ENV_KEYS_WIN = (
    "APPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "PATH",
    "PROCESSOR_ARCHITECTURE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERNAME",
    "USERPROFILE",
)


def _safe_base_env() -> dict[str, str]:
    """A minimal, vetted subset of host env vars safe to pass to an MCP subprocess.

    Excludes the full platform environment (database URLs, API keys, tokens); keeps only
    the variables a process generally needs to run (PATH / HOME / locale / temp dir).
    """
    keys = _SAFE_ENV_KEYS_WIN if os.name == "nt" else _SAFE_ENV_KEYS_POSIX
    return {k: os.environ[k] for k in keys if k in os.environ}


def _subprocess_env(server: McpServerConfig) -> dict[str, str]:
    """Environment for a stdio MCP subprocess: the safe host whitelist plus the server's
    explicitly declared env (which overrides the whitelist for same-named keys). The full
    platform environment is never inherited (mcp-stdio-isolation).
    """
    return {**_safe_base_env(), **server.env}


def _is_tools_list_changed(message: Any) -> bool:
    """Whether an incoming MCP server message is a tools/list_changed notification."""
    root = getattr(message, "root", None)
    return getattr(root, "method", None) == "notifications/tools/list_changed"


def _reregister_stdio_tools(server: McpServerConfig, tools: list[Any], scope: int | None) -> None:
    """Replace a stdio server's tools in the shared registry in place (scope=None only).

    Synchronous and free of await points, so it is atomic w.r.t. other coroutines reading
    the registry in the single-threaded event loop (no dict-changed-during-iteration race).
    Agent-scoped tools are dispatched via call_tool(scope) and never enter the shared
    registry, so a scoped refresh is a no-op here.
    """
    if scope is not None:
        return
    import fleetent.tools.registry as tr

    prefix = f"{server.id}__"
    for name in [n for n in tr._registry if n.startswith(prefix)]:
        del tr._registry[name]
    for tool_def in tools:
        _register_tool_stdio(server, _make_tool_name(server.id, tool_def.name), tool_def, scope)
    _register_utility_tools(server, scope)


async def _refresh_stdio_tools(server: McpServerConfig, scope: int | None, session: Any) -> None:
    """Re-list and re-register a stdio server's tools after a list_changed notification.

    Identity-guarded (ignores a notification from a session that has since been replaced)
    and deduped via a per-server lock (coalesces a burst of notifications).
    """
    if _active_sessions.get((scope, server.id)) is not session:
        return
    if server._list_refresh_lock.locked():
        return
    async with server._list_refresh_lock:
        if _active_sessions.get((scope, server.id)) is not session:
            return
        try:
            tools = await _list_all_tools_stdio(session)
        except Exception as exc:  # noqa: BLE001 — a refresh failure must not break the read loop
            logger.warning("mcp_tools_refresh_failed server_id=%s error=%s", server.id, exc)
            return
        _reregister_stdio_tools(server, tools, scope)
        logger.info("mcp_tools_refreshed server_id=%s tool_count=%d", server.id, len(tools))


def _make_message_handler(server: McpServerConfig, scope: int | None) -> Any:
    """Build a ClientSession message handler that refreshes tools on list_changed.

    The refresh runs in a separate task (never inline) so the handler does not issue a
    request on the stream while it is still processing the notification — the stdio wedge.
    """

    async def handler(message: Any) -> None:
        if not _is_tools_list_changed(message):
            return
        current = _active_sessions.get((scope, server.id))
        if current is not None:
            asyncio.create_task(_refresh_stdio_tools(server, scope, current))

    return handler


async def _register_stdio_server(server: McpServerConfig, scope: int | None = None) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=server.command,
        args=server.args,
        env=_subprocess_env(server),
    )

    stack = await get_exit_stack()
    read, write = await stack.enter_async_context(stdio_client(params))
    session: Any = await stack.enter_async_context(
        ClientSession(read, write, message_handler=_make_message_handler(server, scope))
    )
    init_result = await session.initialize()
    _capture_init_result(server, _init_result_to_dict(init_result))

    _active_sessions[(scope, server.id)] = session
    _server_registry[(scope, server.id)] = server

    tools = await _list_all_tools_stdio(session)
    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def.name)
        _register_tool_stdio(server, tool_name, tool_def, scope)

    logger.info(
        "mcp_server_registered server_id=%s transport=stdio tool_count=%d", server.id, len(tools)
    )
    _register_utility_tools(server, scope)


PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "fleetent", "version": "1.0"}


def _capture_init_result(server: McpServerConfig, result: Any) -> None:
    """Capture negotiated protocolVersion + advertised capabilities from an initialize result.

    Falls back to the client's PROTOCOL_VERSION when the server omits a version, and to an
    empty capabilities mapping when none is advertised. Per-server state, never global.
    """
    if not isinstance(result, dict):
        server.protocol_version = server.protocol_version or PROTOCOL_VERSION
        return
    server.protocol_version = result.get("protocolVersion") or PROTOCOL_VERSION
    caps = result.get("capabilities")
    server.capabilities = caps if isinstance(caps, dict) else {}


def _init_result_to_dict(init_result: Any) -> dict[str, Any]:
    """Coerce an SDK InitializeResult (stdio) into a {protocolVersion, capabilities} dict."""
    if init_result is None:
        return {}
    caps = getattr(init_result, "capabilities", None)
    caps_dict: dict[str, Any] = {}
    dump = getattr(caps, "model_dump", None)
    if callable(dump):
        try:
            caps_dict = dump(exclude_none=True)
        except Exception:  # noqa: BLE001 — fall back to empty caps if the model cannot dump
            caps_dict = {}
    elif isinstance(caps, dict):
        caps_dict = caps
    return {
        "protocolVersion": getattr(init_result, "protocolVersion", None),
        "capabilities": caps_dict,
    }


def _base_headers(server: McpServerConfig, *, bearer: str | None = None) -> dict[str, str]:
    """Build request headers: Accept negotiation, optional Bearer auth, session id echo.

    Stays synchronous and pure assembly (D6a method a): the api_key Bearer is read from
    the environment here, while the oauth2 Bearer is resolved asynchronously by the caller
    before header construction and passed in via ``bearer`` — never fetched inside this
    sync function.
    """
    headers: dict[str, str] = {"Accept": "application/json, text/event-stream"}
    if server.headers:
        headers.update(server.headers)
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    if server.session_id:
        headers["Mcp-Session-Id"] = server.session_id
    # MCP 2025-06-18: echo the negotiated protocol version on requests issued after the
    # initialize handshake (protocol_version is set only once a session is established).
    if server.protocol_version:
        headers["MCP-Protocol-Version"] = server.protocol_version
    return headers


def _clear_oauth_auth_state(server: McpServerConfig) -> None:
    """Clear sticky auth-unavailable flag and cached token (D5 recovery trigger).

    Called on (re-)registration / config reload so updated credentials take effect on the
    next resolve. Recovery is by this explicit signal, not by timed backoff.
    """
    server._auth_unavailable = False
    server._token_store.clear(server.id)


def _token_is_valid(token: OAuthToken | None) -> bool:
    if token is None:
        return False
    return _now() < token.expires_at


def _is_transient_token_error(exc: Exception) -> bool:
    """Whether a token-endpoint failure is transient (D5: must NOT be sticky).

    5xx / network / timeout errors mean the authorization server hiccupped, not that the
    credentials are wrong — these are retryable. Only genuine auth errors (401 /
    invalid_client / invalid_grant) are sticky and surface as OAuthAuthUnavailableError.
    """
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def _is_auth_error_response(resp: Any) -> bool:
    """Whether a token-endpoint response indicates a genuine credential/auth error (D5)."""
    if resp.status_code == 401:
        return True
    if resp.status_code in (400, 403):
        try:
            err = resp.json().get("error")
        except Exception:  # noqa: BLE001 — non-JSON 4xx still classified below
            err = None
        return err in ("invalid_client", "invalid_grant", "unauthorized_client")
    return False


async def _fetch_client_credentials_token(server: McpServerConfig) -> OAuthToken:
    """POST grant_type=client_credentials to the token endpoint and parse the token (D1).

    Raises OAuthAuthUnavailableError on a genuine auth error (sticky). Transient failures
    (5xx / network / timeout) propagate as httpx errors so callers treat them as retryable.
    """
    import httpx

    secret = os.environ.get(server.client_secret_env, "") if server.client_secret_env else ""
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": server.client_id,
        "client_secret": secret,
    }
    if server.scope:
        data["scope"] = server.scope

    async with httpx.AsyncClient(timeout=server.connect_timeout, follow_redirects=True) as client:
        resp = await client.post(server.token_url, data=data)

    if _is_auth_error_response(resp):
        raise OAuthAuthUnavailableError(
            f"OAuth2 authentication unavailable for server '{server.id}': token endpoint "
            f"rejected the credentials (status={resp.status_code}). Re-authorize or check the "
            f"OAuth2 credentials (client_id / {server.client_secret_env})."
        )
    resp.raise_for_status()  # transient 5xx surfaces as retryable HTTPStatusError

    body = resp.json()
    access_token = body.get("access_token")
    if not access_token:
        raise OAuthAuthUnavailableError(
            f"OAuth2 token response for server '{server.id}' has no access_token."
        )
    expires_in = body.get("expires_in")
    ttl = float(expires_in) if expires_in is not None else _OAUTH_DEFAULT_TTL
    expires_at = _now() + ttl - _OAUTH_EXPIRY_SAFETY_MARGIN
    return OAuthToken(
        access_token=access_token,
        expires_at=expires_at,
        refresh_token=body.get("refresh_token"),
    )


async def _resolve_oauth_token(server: McpServerConfig) -> str:
    """Resolve a valid access token for an oauth2 server, refreshing if needed (D4/D9).

    Short-circuits if the server is already marked auth-unavailable (D5/D8). Serializes
    fetch/refresh through the server's own asyncio.Lock and double-checks the cached token
    inside the lock so concurrent callers coalesce into a single token request (D9).
    On a genuine auth error sets the sticky flag; transient errors propagate without it.
    """
    if server._auth_unavailable:
        raise OAuthAuthUnavailableError(
            f"OAuth2 authentication unavailable for server '{server.id}'. Re-authorize or "
            f"check the OAuth2 credentials."
        )

    cached = server._token_store.get(server.id)
    if _token_is_valid(cached):
        assert cached is not None
        return cached.access_token

    async with server._refresh_lock:
        cached = server._token_store.get(server.id)
        if _token_is_valid(cached):
            assert cached is not None
            return cached.access_token
        try:
            token = await _fetch_client_credentials_token(server)
        except OAuthAuthUnavailableError:
            server._auth_unavailable = True  # sticky: stop retrying with bad credentials
            raise
        server._token_store.set(
            server.id,
            access_token=token.access_token,
            expires_at=token.expires_at,
            refresh_token=token.refresh_token,
        )
        return token.access_token


async def _bearer_for(server: McpServerConfig) -> str | None:
    """Resolve the oauth2 Bearer ahead of sync header assembly (D6a); None otherwise."""
    if server.auth_type == "oauth2":
        return await _resolve_oauth_token(server)
    return None


def _parse_jsonrpc_response(resp: Any, request_id: int) -> dict[str, Any]:
    """Parse a JSON or SSE response into the JSON-RPC object matching request_id."""
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return _extract_jsonrpc_from_sse(resp.text, request_id)
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected JSON-RPC response shape")
    return data


def _is_session_expired(resp: Any) -> bool:
    """Whether an HTTP response indicates an expired/invalid Mcp-Session-Id (D1).

    HTTP 404 is the primary anchor for a server rejecting a stale session. Other 4xx
    statuses are treated as session expiry only when an explicit session-invalid marker
    is present in the response (header or body). 401/403 are authentication errors and
    MUST NOT be treated as session expiry — they propagate so callers/MCP5 can handle
    them rather than triggering a session rebuild.
    """
    status = resp.status_code
    if status == 404:
        return True
    if status in (401, 403):
        return False
    if 400 <= status < 500:
        return _has_session_invalid_marker(resp)
    return False


def _has_session_invalid_marker(resp: Any) -> bool:
    """Whether a 4xx response carries an explicit session-invalid marker (header/body)."""
    if resp.headers.get("Mcp-Session-Invalid"):
        return True
    try:
        body = resp.text.lower()
    except Exception:  # noqa: BLE001 — marker detection must not mask the real error
        return False
    return "session" in body and ("expired" in body or "invalid" in body or "not found" in body)


async def _open_session(client: Any, server: McpServerConfig) -> None:
    """Open a session: send initialize, store the Mcp-Session-Id, send initialized.

    This is the handshake shared by initial registration and session rebuild; the
    session id lives on the server instance (no module-level session table).
    """
    request_id = _next_request_id(server)
    bearer = await _bearer_for(server)
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
        headers=_base_headers(server, bearer=bearer),
    )
    init_resp.raise_for_status()
    session_id = init_resp.headers.get("Mcp-Session-Id")
    if session_id:
        server.session_id = session_id
    init_obj = _parse_jsonrpc_response(init_resp, request_id)
    _capture_init_result(server, init_obj.get("result"))
    await _post_notification(client, server, "notifications/initialized")


def _expire_session(server: McpServerConfig) -> None:
    """Clear the server's local session id ahead of a rebuild or on close."""
    server.session_id = None


async def _post_jsonrpc(
    client: Any,
    server: McpServerConfig,
    method: str,
    params: dict[str, Any],
    *,
    _allow_session_retry: bool = True,
) -> dict[str, Any]:
    """Send a JSON-RPC request and return the matched JSON-RPC response object.

    On a session-expiry response (D1), the session is expired, re-opened via initialize,
    and the original request is retried exactly once (guarded by _allow_session_retry).
    Session-expiry detection happens before raise_for_status so the 404/4xx branch is
    reachable (D1a).
    """
    request_id = _next_request_id(server)
    bearer = await _bearer_for(server)
    resp = await client.post(
        f"{server.url}/",
        json={"jsonrpc": "2.0", "method": method, "params": params, "id": request_id},
        headers=_base_headers(server, bearer=bearer),
    )
    if _allow_session_retry and _is_session_expired(resp):
        _expire_session(server)
        await _open_session(client, server)
        return await _post_jsonrpc(client, server, method, params, _allow_session_retry=False)
    resp.raise_for_status()
    obj = _parse_jsonrpc_response(resp, request_id)
    if "error" in obj:
        raise RuntimeError(f"MCP {method} error: {obj['error']}")
    return obj


async def _post_notification(client: Any, server: McpServerConfig, method: str) -> None:
    """Send a JSON-RPC notification (no id, no response expected); tolerate failures."""
    try:
        bearer = await _bearer_for(server)
        await client.post(
            f"{server.url}/",
            json={"jsonrpc": "2.0", "method": method},
            headers=_base_headers(server, bearer=bearer),
        )
    except Exception as exc:  # noqa: BLE001 — notification is best-effort
        logger.debug(
            "mcp_notification_failed server_id=%s method=%s error=%s", server.id, method, exc
        )


async def _list_all_tools_http(client: Any, server: McpServerConfig) -> list[dict[str, Any]]:
    """Fetch every page of tools/list, following nextCursor, bounded by _MAX_TOOL_PAGES."""
    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(_MAX_TOOL_PAGES):
        params: dict[str, Any] = {"cursor": cursor} if cursor else {}
        obj = await _post_jsonrpc(client, server, "tools/list", params)
        result = obj.get("result", {})
        tools.extend(result.get("tools", []) or [])
        cursor = result.get("nextCursor")
        if not cursor:
            return tools
    logger.warning("mcp_tools_list_page_cap server_id=%s cap=%d", server.id, _MAX_TOOL_PAGES)
    return tools


async def _list_all_tools_stdio(session: Any) -> list[Any]:
    """Fetch every page of stdio list_tools, following nextCursor, bounded by _MAX_TOOL_PAGES."""
    tools: list[Any] = []
    cursor: str | None = None
    for _ in range(_MAX_TOOL_PAGES):
        result = await session.list_tools(cursor=cursor)
        tools.extend(result.tools or [])
        cursor = getattr(result, "nextCursor", None)
        if not cursor:
            return tools
    logger.warning("mcp_tools_list_page_cap transport=stdio cap=%d", _MAX_TOOL_PAGES)
    return tools


async def _register_http_server(server: McpServerConfig, scope: int | None = None) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=server.connect_timeout, follow_redirects=True) as client:
        await _open_session(client, server)
        tools = await _list_all_tools_http(client, server)

    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def["name"])
        _register_tool_http(server, tool_name, tool_def, scope)

    _server_registry[(scope, server.id)] = server
    logger.info(
        "mcp_server_registered server_id=%s transport=http tool_count=%d", server.id, len(tools)
    )
    _register_utility_tools(server, scope)


async def probe_server(server: McpServerConfig) -> dict[str, Any]:
    """One-shot connectivity check for the admin "Test" action.

    Connects, runs the initialize handshake, and lists tools — then discards the
    connection. Never mutates the shared registry/sessions, so it is safe to run
    against an unregistered or candidate config. Returns connected/tool_count/tools,
    or connected=False with the error string on any failure.
    """
    try:
        if server.transport == "stdio":
            tools = await _probe_stdio_tools(server)
        else:
            tools = await _probe_http_tools(server)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a clean result
        return {"connected": False, "error": str(exc)}
    return {"connected": True, "tool_count": len(tools), "tools": tools}


async def _probe_http_tools(server: McpServerConfig) -> list[dict[str, str]]:
    import httpx

    async with httpx.AsyncClient(timeout=server.connect_timeout, follow_redirects=True) as client:
        await _open_session(client, server)
        tools = await _list_all_tools_http(client, server)
    return [{"name": t["name"], "description": t.get("description", "")} for t in tools]


async def _probe_stdio_tools(server: McpServerConfig) -> list[dict[str, str]]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=server.command, args=server.args, env=_subprocess_env(server)
    )
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session: Any = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools = await _list_all_tools_stdio(session)
        return [{"name": t.name, "description": t.description or ""} for t in tools]


def unregister_server(server_id: str, scope: int | None = None) -> None:
    """Remove a server's tools and registry/session entries (e.g. on delete/disable).

    The inverse of registration: drops every ``{server_id}__`` tool from the shared
    tool registry and forgets the server so its tools stop being exposed. Best-effort
    on the session handle; an HTTP DELETE handshake is not attempted here.
    """
    import fleetent.tools.registry as tr

    prefix = f"{server_id}__"
    if scope is None:
        for name in [n for n in tr._registry if n.startswith(prefix)]:
            del tr._registry[name]
    _server_registry.pop((scope, server_id), None)
    _active_sessions.pop((scope, server_id), None)


def _rewrite_refs(node: Any) -> Any:
    """Recursively rewrite ``#/definitions/...`` $ref strings to ``#/$defs/...``."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/definitions/"):
                out[key] = "#/$defs/" + value[len("#/definitions/") :]
            else:
                out[key] = _rewrite_refs(value)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    return node


def _sanitize_input_schema(schema: Any) -> dict[str, Any]:
    """Normalize a server-provided input schema into a provider-safe object schema.

    Conservative and meaning-preserving: guarantee a top-level ``type: object`` and a
    ``properties`` map; rename a top-level ``definitions`` block to ``$defs`` (only when
    ``$defs`` is absent, to avoid clobbering) and rewrite ``#/definitions/`` refs to match.
    Works on a copy and never raises — a malformed schema falls back to a safe default.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    try:
        out = copy.deepcopy(schema)
        if "definitions" in out and "$defs" not in out:
            out["$defs"] = out.pop("definitions")
            out = _rewrite_refs(out)
        if out.get("type") != "object":
            out["type"] = "object"
        if not isinstance(out.get("properties"), dict):
            out["properties"] = {}
        return out
    except Exception:  # noqa: BLE001 — sanitization must never break registration
        return {"type": "object", "properties": {}}


def _register_tool_stdio(
    server: McpServerConfig, tool_name: str, tool_def: Any, scope: int | None = None
) -> None:
    import fleetent.tools.registry as tr

    raw_schema = tool_def.inputSchema if hasattr(tool_def, "inputSchema") else None
    input_schema = _sanitize_input_schema(raw_schema)

    async def call(**kwargs: object) -> str:
        return await _call_stdio_tool(server.id, tool_def.name, dict(kwargs), server._agent_scope)

    schema: tr.ToolSchema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_def.description or "",
            "parameters": input_schema,
        },
    }
    # Only globally-registered (scope=None) tools enter the shared schema/registry;
    # agent-scoped tools are dispatched via call_tool(scope) to avoid name collisions.
    if scope is None:
        tr._registry[tool_name] = (call, schema)


def _register_tool_http(
    server: McpServerConfig, tool_name: str, tool_def: dict[str, Any], scope: int | None = None
) -> None:
    import fleetent.tools.registry as tr

    input_schema = _sanitize_input_schema(tool_def.get("inputSchema"))

    async def call(**kwargs: object) -> str:
        return await _call_http_tool(server.id, tool_def["name"], dict(kwargs), server._agent_scope)

    schema: tr.ToolSchema = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_def.get("description", ""),
            "parameters": input_schema,
        },
    }
    if scope is None:
        tr._registry[tool_name] = (call, schema)


# === MCP result normalization (mcp-result-fidelity) =========================
# A CallToolResult carries an ordered list of content blocks (text / image / audio /
# embedded resource), an optional structuredContent, and an isError flag. The stdio
# path yields typed SDK objects (attribute access) while the http path yields JSON
# dicts; both are normalized here through one duck-typed path.

_TOOL_ERROR_PREFIX = "MCP tool error: "


def _field(block: Any, key: str, default: Any = None) -> Any:
    """Read a field from a content block that may be a dict or an SDK object."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _approx_bytes(data: Any) -> int:
    """Best-effort decoded size of a base64 payload (0 when not a non-empty string)."""
    if not isinstance(data, str) or not data:
        return 0
    return (len(data) * 3) // 4


def _media_marker(kind: str, mime: Any, data: Any) -> str:
    """Concise textual marker for non-text content — never the raw payload."""
    mime_str = mime if isinstance(mime, str) and mime else "application/octet-stream"
    size = _approx_bytes(data)
    return f"[{kind}: {mime_str}, ~{size} bytes]" if size else f"[{kind}: {mime_str}]"


def _block_to_text(block: Any) -> str:
    """Render one MCP content block as text, for dict or SDK-object shapes.

    Text blocks return their text; image/audio return a concise marker; an embedded
    resource inlines its text when present, else a marker. Binary payloads are never
    emitted as raw base64, and unknown blocks degrade to a short marker, never raise.
    """
    btype = _field(block, "type")
    text = _field(block, "text")
    if isinstance(text, str) and text:
        return text
    if btype in ("image", "audio"):
        return _media_marker(btype, _field(block, "mimeType"), _field(block, "data"))
    if btype == "resource":
        resource = _field(block, "resource")
        if resource is not None:
            rtext = _field(resource, "text")
            if isinstance(rtext, str) and rtext:
                return rtext
            marker = _media_marker(
                "resource", _field(resource, "mimeType"), _field(resource, "blob")
            )
            uri = _field(resource, "uri")
            return f"{marker[:-1]} {uri}]" if isinstance(uri, str) and uri else marker
        return "[resource]"
    if btype == "resource_link":
        uri = _field(block, "uri")
        return f"[resource_link: {uri}]" if isinstance(uri, str) and uri else "[resource_link]"
    return f"[{btype}]" if isinstance(btype, str) and btype else "[content]"


def _normalize_tool_result(content_blocks: Any, *, structured_content: Any, is_error: bool) -> str:
    """Normalize an MCP CallToolResult into the string returned to the agent.

    Aggregates all content blocks (not just the first), falls back to JSON-serialized
    structuredContent when there are no content blocks, and marks isError results with a
    pedagogical prefix so the agent can read and recover. Never raises on odd shapes.
    """
    parts = [_block_to_text(b) for b in (content_blocks or [])]
    parts = [p for p in parts if p]
    if parts:
        text = "\n".join(parts)
    elif structured_content is not None:
        text = json.dumps(structured_content, ensure_ascii=False, default=str)
    else:
        text = ""
    if is_error:
        return f"{_TOOL_ERROR_PREFIX}{text}" if text else f"{_TOOL_ERROR_PREFIX}(no detail)"
    return text


async def _call_stdio_tool(
    server_id: str, tool_name: str, args: dict[str, Any], scope: int | None = None
) -> str:
    server = _server_registry.get((scope, server_id))
    # D5: short-circuit degraded/unavailable servers without touching the subprocess.
    if server is not None and server._health is not HealthState.healthy:
        return _unavailable_result(server_id)

    session = _active_sessions.get((scope, server_id))
    if session is None:
        raise KeyError(f"No active stdio session for MCP server: {server_id}")
    try:
        result = await session.call_tool(tool_name, args)
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if server is not None and _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise
    return _normalize_tool_result(
        getattr(result, "content", None),
        structured_content=getattr(result, "structuredContent", None),
        is_error=bool(getattr(result, "isError", False)),
    )


async def _call_http_tool(
    server_id: str, tool_name: str, args: dict[str, Any], scope: int | None = None
) -> str:
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")

    # D8: an oauth2 server already marked auth-unavailable returns an error result directly —
    # no token fetch, no request, no raise. Orthogonal to MCP3 connection health.
    if server.auth_type == "oauth2" and server._auth_unavailable:
        return (
            f"MCP server '{server_id}' authentication unavailable: re-authorize or check the "
            f"OAuth2 credentials."
        )

    # D5: short-circuit degraded/unavailable servers without making a network request.
    if server._health is not HealthState.healthy:
        return _unavailable_result(server_id)

    import httpx

    try:
        async with httpx.AsyncClient(timeout=server.call_timeout, follow_redirects=True) as client:
            obj = await _post_jsonrpc(
                client, server, "tools/call", {"name": tool_name, "arguments": args}
            )
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise

    result = obj.get("result")
    if isinstance(result, dict):
        return _normalize_tool_result(
            result.get("content"),
            structured_content=result.get("structuredContent"),
            is_error=bool(result.get("isError", False)),
        )
    return str(result) if result is not None else ""


# Public API. `scope` keys the (scope, server_id) registry: None = global (startup)
# servers; an int = an agent-scoped registration. A scope with no matching server_id
# raises rather than silently falling back to the global server (agent isolation).
async def call_tool(
    server_id: str, tool_name: str, args: dict[str, Any], scope: int | None = None
) -> str:
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    if server.transport == "stdio":
        return await _call_stdio_tool(server_id, tool_name, args, scope)
    return await _call_http_tool(server_id, tool_name, args, scope)


# === MCP resources / prompts as capability-gated synthetic tools ============
# Servers that advertise `resources` / `prompts` get utility tools under their
# {server_id}__ namespace; invoking one dispatches to the matching MCP method and
# returns the result serialized as JSON text.

_UTILITY_METHODS = {
    "list_resources": "resources/list",
    "read_resource": "resources/read",
    "list_prompts": "prompts/list",
    "get_prompt": "prompts/get",
}


def _utility_params(util_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """JSON-RPC params for a utility method, built from the tool-call arguments."""
    if util_name == "read_resource":
        return {"uri": args.get("uri")}
    if util_name == "get_prompt":
        return {"name": args.get("name"), "arguments": args.get("arguments") or {}}
    return {}


def _jsonify(obj: Any) -> str:
    """Serialize a utility result (pydantic object or JSON dict) to text for the agent."""
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            obj = dump(mode="json", exclude_none=True)
        except Exception:  # noqa: BLE001 — fall back to a string view if the model cannot dump
            return str(obj)
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 — never fail a tool call on serialization
        return str(obj)


async def _call_http_utility(server: McpServerConfig, util_name: str, args: dict[str, Any]) -> str:
    import httpx

    method = _UTILITY_METHODS[util_name]
    try:
        async with httpx.AsyncClient(timeout=server.call_timeout, follow_redirects=True) as client:
            obj = await _post_jsonrpc(client, server, method, _utility_params(util_name, args))
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise
    return _jsonify(obj.get("result"))


async def _call_stdio_utility(
    server: McpServerConfig, util_name: str, args: dict[str, Any], scope: int | None
) -> str:
    session = _active_sessions.get((scope, server.id))
    if session is None:
        raise KeyError(f"No active stdio session for MCP server: {server.id}")
    try:
        if util_name == "list_resources":
            result = await session.list_resources()
        elif util_name == "read_resource":
            result = await session.read_resource(args.get("uri"))
        elif util_name == "list_prompts":
            result = await session.list_prompts()
        elif util_name == "get_prompt":
            result = await session.get_prompt(args.get("name"), args.get("arguments"))
        else:
            raise ValueError(f"Unknown MCP utility: {util_name}")
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise
    return _jsonify(result)


async def _call_utility(
    server_id: str, util_name: str, args: dict[str, Any], scope: int | None = None
) -> str:
    """Dispatch a resources/prompts utility tool to its MCP method (auth/health-aware)."""
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    if server.auth_type == "oauth2" and server._auth_unavailable:
        return (
            f"MCP server '{server_id}' authentication unavailable: re-authorize or check the "
            f"OAuth2 credentials."
        )
    if server._health is not HealthState.healthy:
        return _unavailable_result(server_id)
    if server.transport == "stdio":
        return await _call_stdio_utility(server, util_name, args, scope)
    return await _call_http_utility(server, util_name, args)


# (util_name, capability_key, description, parameter schema) for the synthetic tools.
_UTILITY_TOOL_SPECS = (
    (
        "list_resources",
        "resources",
        "List the resources this MCP server exposes.",
        {"type": "object", "properties": {}},
    ),
    (
        "read_resource",
        "resources",
        "Read a resource from this MCP server by its uri.",
        {
            "type": "object",
            "properties": {"uri": {"type": "string", "description": "The resource uri to read."}},
            "required": ["uri"],
        },
    ),
    (
        "list_prompts",
        "prompts",
        "List the prompts this MCP server exposes.",
        {"type": "object", "properties": {}},
    ),
    (
        "get_prompt",
        "prompts",
        "Get a prompt from this MCP server by name, with optional arguments.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The prompt name."},
                "arguments": {"type": "object", "description": "Optional prompt arguments."},
            },
            "required": ["name"],
        },
    ),
)


def _register_utility_tool(
    server: McpServerConfig,
    util_name: str,
    description: str,
    schema: dict[str, Any],
    scope: int | None,
) -> None:
    import fleetent.tools.registry as tr

    tool_name = _make_tool_name(server.id, util_name)

    async def call(**kwargs: object) -> str:
        return await _call_utility(server.id, util_name, dict(kwargs), server._agent_scope)

    tool_schema: tr.ToolSchema = {
        "type": "function",
        "function": {"name": tool_name, "description": description, "parameters": schema},
    }
    tr._registry[tool_name] = (call, tool_schema)


def _register_utility_tools(server: McpServerConfig, scope: int | None) -> None:
    """Register resources/prompts synthetic tools for a server, gated by its advertised
    capabilities. Only the global (scope=None) registration enters the shared registry,
    consistent with regular tool registration.
    """
    if scope is not None:
        return
    caps = server.capabilities or {}
    for util_name, cap_key, description, schema in _UTILITY_TOOL_SPECS:
        if cap_key in caps:
            _register_utility_tool(server, util_name, description, schema, scope)
