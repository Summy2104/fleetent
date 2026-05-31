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
import json
import logging
import os
import time
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fleetent.error_classifier import ErrorClassification

logger = logging.getLogger(__name__)

_server_registry: dict[str, McpServerConfig] = {}
_active_sessions: dict[str, Any] = {}  # server_id -> mcp.ClientSession (stdio only)
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
    # HTTP fields
    url: str = ""
    auth_type: str = "none"  # "none" | "api_key" | "oauth2"
    api_key_env: str = ""
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
    # Streamable HTTP runtime state (per-server, not module-level global)
    session_id: str | None = None  # assigned by server via Mcp-Session-Id on initialize
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
    from fleetent.error_classifier import CLASSIFICATION_TABLE, ErrorCategory

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
    """
    server = _server_registry.get(server_id)
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
        if _active_sessions.get(server.id) is None:
            set_health(server, HealthState.degraded)
            _schedule_reconnect(server)
        return

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
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

    async with httpx.AsyncClient(timeout=10.0) as client:
        for server in active:
            try:
                bearer = await _bearer_for(server)
                await client.delete(f"{server.url}/", headers=_base_headers(server, bearer=bearer))
            except Exception as exc:  # noqa: BLE001 — DELETE is best-effort on shutdown
                logger.debug("mcp_session_delete_failed server_id=%s error=%s", server.id, exc)
            finally:
                _expire_session(server)


async def register_all(servers: list[McpServerConfig]) -> None:
    for server in servers:
        try:
            await _register_server(server)
        except Exception as exc:
            logger.warning("mcp_server_unavailable server_id=%s error=%s", server.id, exc)


async def _register_server(server: McpServerConfig) -> None:
    if server.auth_type == "oauth2":
        _clear_oauth_auth_state(server)  # (re-)registration clears sticky auth state (D5)
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


def _base_headers(server: McpServerConfig, *, bearer: str | None = None) -> dict[str, str]:
    """Build request headers: Accept negotiation, optional Bearer auth, session id echo.

    Stays synchronous and pure assembly (D6a method a): the api_key Bearer is read from
    the environment here, while the oauth2 Bearer is resolved asynchronously by the caller
    before header construction and passed in via ``bearer`` — never fetched inside this
    sync function.
    """
    headers: dict[str, str] = {"Accept": "application/json, text/event-stream"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    if server.session_id:
        headers["Mcp-Session-Id"] = server.session_id
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

    async with httpx.AsyncClient(timeout=10.0) as client:
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
    _parse_jsonrpc_response(init_resp, request_id)
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


async def _register_http_server(server: McpServerConfig) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        await _open_session(client, server)
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
    server = _server_registry.get(server_id)
    # D5: short-circuit degraded/unavailable servers without touching the subprocess.
    if server is not None and server._health is not HealthState.healthy:
        return _unavailable_result(server_id)

    session = _active_sessions.get(server_id)
    if session is None:
        raise KeyError(f"No active stdio session for MCP server: {server_id}")
    try:
        result = await session.call_tool(tool_name, args)
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if server is not None and _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise
    if result.content:
        return result.content[0].text
    return ""


async def _call_http_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    server = _server_registry.get(server_id)
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            obj = await _post_jsonrpc(
                client, server, "tools/call", {"name": tool_name, "arguments": args}
            )
    except Exception as exc:  # noqa: BLE001 — disconnects map to mcp_disconnect (D1); rest re-raised
        if _is_disconnect_error(exc):
            return _handle_disconnect(server)
        raise

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
