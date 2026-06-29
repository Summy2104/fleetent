"""MCP (Model Context Protocol) client for connecting to external tool servers.

All transports go through the official `mcp` SDK's ClientSession over a transport-specific
stream pair, held alive in a module-level AsyncExitStack:
  - stdio: `stdio_client` (subprocess stdin/stdout)
  - http:  `streamable_http_client(url, http_client=...)` (Streamable HTTP; the legacy
           `streamablehttp_client(headers=,auth=)` entry is kept as a re-export shim)
  - sse:   `sse_client` (legacy Server-Sent Events)

The SDK owns the wire protocol (JSON-RPC, initialize handshake, session id, Accept
negotiation, SSE parsing, protocol-version negotiation). This module keeps the
application/operational layer: tool registration ({server_id}__{tool_name}), result
normalization, degradation/visibility, schema sanitization, header/env: resolution,
scope isolation, and lazy reconnect on a dropped session.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Generator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from fleetent.integrations.mcp import authorization as _authz
from fleetent.integrations.mcp.per_user_tokens import UserToken, resolve_user_token
from fleetent.integrations.mcp.tool_naming import Projector, make_projector
from mcp import ClientSession
from mcp.client.auth import OAuthFlowError, OAuthTokenError
from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata
from mcp.shared.auth import OAuthToken as SdkOAuthToken
from mcp.types import LATEST_PROTOCOL_VERSION

logger = logging.getLogger(__name__)

_server_registry: dict[tuple[int | None, str], McpServerConfig] = {}
# Ids of strict-mode servers that failed to register at startup (MCP4 D5): not in
# _server_registry (never registered) yet still strict-unavailable for the query.
_failed_strict_servers: set[str] = set()
# Live-session key (mcp-per-user-oauth2 D2). A plain server keeps the historical 2-tuple
# (scope, server_id) — byte-identical to the pre-per-user keying. A per-user oauth server
# (oauth_grant == "authorization_code") uses a 3-tuple (scope, server_id, user_id) so each
# user gets an isolated session/process. Keys are heterogeneous on purpose: the spec
# requires non-per-user keys to remain (scope, server_id) exactly.
SessionKey = tuple[int | None, str] | tuple[int | None, str, str | None]
_active_sessions: dict[SessionKey, Any] = {}  # session key -> ClientSession
# session key -> session host. Each MCP session is owned by a dedicated task
# (_SessionHost.task) so the SDK transport's anyio cancel scope is entered AND exited in
# the same task — a shared module-level AsyncExitStack unwound from another task crashes
# the process on teardown (2026-06-11 graceful-shutdown crash).
_session_hosts: dict[SessionKey, _SessionHost] = {}
_HOST_CLOSE_TIMEOUT = 5.0  # seconds to await a host's graceful teardown before cancelling

# stdio per-user subprocess pool sizing/lifetime (mcp-per-user-oauth2 D4). Injectable so
# tests drive tiny values; production defaults keep the PID/memory footprint bounded since
# a per-user stdio server costs one subprocess per (user × server).
_STDIO_IDLE_TIMEOUT = 600.0  # seconds a per-user stdio host may sit idle before reaping
_STDIO_MAX_TOTAL = 64  # global cap on live per-user stdio subprocesses
_STDIO_MAX_PER_USER = 8  # per-user cap on live per-user stdio subprocesses (across servers)
_STDIO_REAP_INTERVAL = 60.0  # background reaper sweep cadence


def _stdio_clock() -> float:
    """Monotonic time source for the stdio pool (idle/LRU/expiry); patched in tests."""
    return time.monotonic()


_MAX_TOOL_PAGES = 100  # tools/list pagination safety cap: stop following nextCursor past this

_UNAVAILABLE_RESULT_PREFIX = "MCP server"  # tool result text on degraded/unavailable (D5)


class HealthState(StrEnum):
    """Connection health of an MCP server (D2). str-valued for trace output.

    With lazy reconnect there is no background prober: a server stays ``healthy`` until a
    call hits a disconnect, then a single in-line reopen+retry decides ``healthy`` (retry
    succeeded) or ``unavailable`` (reopen/retry failed). ``unavailable`` drops its tools
    from the schema filter and short-circuits later calls until a re-registration.
    """

    healthy = "healthy"  # connection live, tools callable
    degraded = "degraded"  # disconnect seen; reopen+retry in flight on the current call
    unavailable = "unavailable"  # reopen/retry failed; tools hidden until re-registration


class OAuthAuthUnavailableError(RuntimeError):
    """Raised when an oauth2 server's credentials/authorization are unusable (D5).

    Signals a sticky "authentication unavailable" condition (token endpoint returned
    401 / invalid_client / invalid_grant): retrying with the same credentials is futile,
    so callers stop and surface re-authorization guidance.
    """


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
    # OAuth2 grant selector (mcp-per-user-oauth2): "client_credentials" (machine identity,
    # the historical default) or "authorization_code" (per-user delegation). The two paths
    # coexist; client_credentials behavior is unchanged when this stays at the default.
    # authorization_endpoint / redirect_path are authorization_code-only (empty otherwise).
    oauth_grant: str = "client_credentials"
    authorization_endpoint: str = ""
    redirect_path: str = ""
    # stdio per-user oauth (mcp-per-user-oauth2 D4): env var name the user's access token is
    # injected under at subprocess spawn. Empty → the module default _DEFAULT_STDIO_TOKEN_ENV.
    # Only consulted for a per-user oauth stdio server; every other server ignores it entirely
    # (no token var is ever injected), so plain stdio env stays byte-identical.
    token_env: str = ""
    # per-user dynamic api-key/bearer (mcp-per-user-apikey): server-level method settings.
    # header_style decides injection (Authorization: Bearer | X-API-Key); credential_input
    # gates submission methods (form|tool|both). Only consulted for an api_key_per_user server.
    header_style: str = "bearer"
    credential_input: str = "form"
    # stdio fields
    command: str = ""  # e.g. "npx" or "python"
    args: list[str] = field(
        default_factory=list
    )  # e.g. ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env: dict[str, str] = field(default_factory=dict)  # extra env vars for the subprocess
    # unified-file-exchange: optional escape hatches for the /exchange namespace.
    # `file_root` declares this server's effective file root explicitly (overrides the
    # convention + any XDG_DATA_HOME); `file_isolation: "off"` opts the server out of the
    # convention env injection entirely (reads the host's real ~/.config etc.).
    file_root: str = ""
    file_isolation: str = "on"  # "on" | "off"
    # Approval rules (approval-boundary-redesign D4): which of this server's operations require
    # approval. Installed into governance.approval_policy at registration. Empty = no-approval.
    approval_rules: list[Any] = field(default_factory=list)
    # Per-server HTTP timeouts in seconds: connect/discovery/probe/token vs tool call.
    connect_timeout: float = 10.0
    call_timeout: float = 30.0
    # Negotiated protocol version + server-advertised capabilities, captured at initialize
    # (per-server runtime state, never module-level global; capabilities gate later features).
    protocol_version: str | None = field(default=None, repr=False, compare=False)
    capabilities: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    # OAuth2 sticky auth-unavailable flag (D5: per-server; token cache lives in the SDK
    # provider's storage, not here). Cleared on (re-)registration by _clear_oauth_auth_state.
    _auth_unavailable: bool = field(default=False, repr=False, compare=False)
    # MCP3 connection-health state, held per-server (D2: never module-level global).
    _health: HealthState = field(default=HealthState.healthy, repr=False, compare=False)
    _reconnect_attempts: int = field(default=0, repr=False, compare=False)
    # Coalesces tools/list_changed-driven refreshes for this stdio server (mcp-dynamic-tools).
    _list_refresh_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, repr=False, compare=False
    )
    # unified-file-exchange: serializes the "call + product-dir diff" window per server so
    # concurrent calls cannot mis-attribute each other's newly-written files (D2 diff layer).
    _call_window_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    # mcp-per-user-oauth2 (D2): per-user call-window locks for a per-user oauth server, so
    # distinct users' concurrent calls don't serialize against each other. Keyed by user_id;
    # lazily populated. Non-per-user servers never touch this and keep _call_window_lock.
    _per_user_call_window_locks: dict[str, asyncio.Lock] = field(
        default_factory=dict, repr=False, compare=False
    )
    # Agent-scope key dimension (next<-main integration): registries/sessions are keyed
    # by (agent_scope, id) so the same server id can carry distinct credentials/sessions
    # per agent. None = the global (startup) scope. Distinct from the oauth `scope` str.
    _agent_scope: int | None = field(default=None, repr=False, compare=False)
    # unified-file-exchange: the agent home this server is registered under, supplied by
    # the agent-side caller (register_all). Drives the stdio cwd + convention env and the
    # /exchange effective-root binding. None = legacy (no convention; byte-identical).
    _agent_home: Path | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_degrade_mode(self)

    @classmethod
    def from_settings(cls, s: Any) -> McpServerConfig:
        """Build a runtime config from an ``McpServerSettings``-like object (duck-typed).

        Hoists the agent.yaml ``x-fleetent`` extensions (degrade_mode / file_root /
        file_isolation / self-hosted OAuth / approval_rules) onto the runtime config.
        Duck-typed on attributes so this module need not import ``fleetent.config``.
        """
        auth = getattr(s, "auth", None)
        if auth is not None:
            auth_type = getattr(auth, "type", "oauth2") or "oauth2"
            token_url = getattr(auth, "token_url", "")
            client_id = _resolve_env_ref(getattr(auth, "client_id", ""))
            client_secret_env = getattr(auth, "client_secret_env", "")
            scope = getattr(auth, "scope", "")
            oauth_grant = getattr(auth, "grant", "client_credentials") or "client_credentials"
            authorization_endpoint = getattr(auth, "authorization_endpoint", "")
            redirect_path = getattr(auth, "redirect_path", "")
            token_env = getattr(auth, "token_env", "")
        else:
            auth_type = getattr(s, "auth_type", "none")
            token_url = client_id = client_secret_env = scope = ""
            oauth_grant = "client_credentials"
            authorization_endpoint = redirect_path = ""
            token_env = ""
        return cls(
            id=s.id,
            transport=s.transport,
            url=getattr(s, "url", ""),
            auth_type=auth_type,
            api_key_env=getattr(s, "api_key_env", ""),
            token_url=token_url,
            client_id=client_id,
            client_secret_env=client_secret_env,
            scope=scope,
            oauth_grant=oauth_grant,
            authorization_endpoint=authorization_endpoint,
            redirect_path=redirect_path,
            token_env=token_env,
            header_style=getattr(s, "header_style", "bearer"),
            credential_input=getattr(s, "credential_input", "form"),
            command=getattr(s, "command", ""),
            args=list(getattr(s, "args", []) or []),
            env=dict(getattr(s, "env", {}) or {}),
            headers=dict(getattr(s, "headers", {}) or {}),
            connect_timeout=getattr(s, "connect_timeout", 10.0),
            call_timeout=getattr(s, "call_timeout", 30.0),
            degrade_mode=getattr(s, "degrade_mode", "degrade"),
            file_root=getattr(s, "file_root", ""),
            file_isolation=getattr(s, "file_isolation", "on"),
            approval_rules=list(getattr(s, "approval_rules", []) or []),
        )


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


# ── tool-name projection (mcp-tool-name-projection) ──────────────────────────
# The registry keys MCP tools by the canonical `{server}__{tool}` name; the model sees a
# configurable PROJECTED name. The reverse table is the source of truth for resolving a
# model's tool call back to canonical — never by string-splitting the projected name (the
# single-underscore presets are ambiguous). This state is agent-process-local runtime
# state (built at registration), never persisted and never platform-side.
_mcp_tool_meta: dict[str, tuple[str, str]] = {}  # canonical -> (server_id, raw_tool)
_projector: Projector = make_projector("claude")
_forward: dict[str, str] = {}  # canonical -> projected
_reverse: dict[str, str] = {}  # projected -> canonical


def set_tool_naming(tool_naming: Any) -> None:
    """Set the active tool-name projection and rebuild the canonical↔projected maps."""
    global _projector
    _projector = make_projector(tool_naming)
    _forward.clear()
    _reverse.clear()
    for canonical, (server_id, raw_tool) in _mcp_tool_meta.items():
        projected = _projector.project(server_id, raw_tool)
        _forward[canonical] = projected
        _reverse[projected] = canonical


def _record_tool_identity(canonical: str, server_id: str, raw_tool: str) -> None:
    """Record an MCP tool's canonical identity and its projection under the active projector."""
    _mcp_tool_meta[canonical] = (server_id, raw_tool)
    projected = _projector.project(server_id, raw_tool)
    _forward[canonical] = projected
    _reverse[projected] = canonical


def _forget_tool_identity(canonical: str) -> None:
    _mcp_tool_meta.pop(canonical, None)
    projected = _forward.pop(canonical, None)
    if projected is not None:
        _reverse.pop(projected, None)


def project_tool_name(canonical: str) -> str:
    """Canonical → model-facing projected name (passthrough for non-MCP tools)."""
    return _forward.get(canonical, canonical)


def resolve_tool_name(projected: str) -> str:
    """Model-facing projected name → canonical (passthrough for non-MCP tools)."""
    return _reverse.get(projected, projected)


def mcp_tool_identity(canonical: str) -> tuple[str, str] | None:
    """Return ``(server_id, raw_tool)`` for a canonical MCP tool name, else None."""
    return _mcp_tool_meta.get(canonical)


def project_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return tool schemas with MCP names projected to model-facing names (copy on rename)."""
    out: list[dict[str, Any]] = []
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        projected = _forward.get(name)
        if projected is None or projected == name:
            out.append(schema)
            continue
        renamed = copy.deepcopy(schema)
        renamed["function"]["name"] = projected
        out.append(renamed)
    return out


def get_registered_server(server_id: str) -> McpServerConfig | None:
    """Public lookup of a registered server config by id (any agent scope), or None.

    Used by managed per-user OAuth wiring to read a server's flattened OAuth fields when
    registering pending-auth, without importing the internal registry across packages.
    """
    for (_scope, sid), server in _server_registry.items():
        if sid == server_id:
            return server
    return None


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


def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"


# === mcp-per-user-oauth2: per-user session-key dimension (D2) ===============


def _is_per_user_oauth(server: McpServerConfig) -> bool:
    """Whether a server uses per-user OAuth delegation (authorization_code grant).

    Only these servers extend the live-session key with a user dimension; every other
    server (no oauth, or client_credentials machine identity) keeps the historical
    ``(scope, server_id)`` keying unchanged. The predicate is the single switch the
    key/lock helpers branch on, so the per-user vs plain paths never diverge by hand.
    """
    return server.auth_type == "oauth2" and server.oauth_grant == "authorization_code"


def _is_per_user_apikey(server: McpServerConfig) -> bool:
    """Whether a server uses per-user dynamic api-key/bearer (mcp-per-user-apikey).

    Like per-user oauth it isolates by (user, agent, server) and is injected per-request, but
    the user supplies a static secret (no OAuth dance, no refresh); the header is chosen by
    ``header_style`` (``Authorization: Bearer`` | ``X-API-Key``).
    """
    return server.auth_type == "api_key_per_user"


def _is_per_user_credential(server: McpServerConfig) -> bool:
    """Whether a server uses any per-user credential (oauth delegation OR dynamic api-key).

    The single switch the shared per-user machinery branches on — session keying, stdio
    per-user pool, call-window locks, token getter — so oauth and api-key per-user paths
    never diverge by hand. OAuth-only concerns (refresh) keep using ``_is_per_user_oauth``.
    """
    return _is_per_user_oauth(server) or _is_per_user_apikey(server)


def _session_key(server: McpServerConfig, scope: int | None, user_id: str | None) -> SessionKey:
    """Compute the live-session/host key for a server under (scope, user).

    Centralizes the keying so every read/write of ``_active_sessions`` / ``_session_hosts``
    agrees on the shape: a plain server keeps the legacy 2-tuple ``(scope, server_id)``
    (byte-identical), a per-user oauth server uses ``(scope, server_id, user_id)`` so each
    user is isolated. The two shapes coexist in the same dicts by design.
    """
    if _is_per_user_credential(server):
        return (scope, server.id, user_id)
    return (scope, server.id)


# Default env var name a per-user oauth stdio server's access token is injected under when
# the config leaves `token_env` empty (mcp-per-user-oauth2 D4). Only ever set for per-user
# oauth stdio subprocesses; plain stdio servers never see it.
_DEFAULT_STDIO_TOKEN_ENV = "MCP_OAUTH_ACCESS_TOKEN"


def _stdio_token_env_name(server: McpServerConfig) -> str:
    """The env var name a per-user oauth stdio server's access token spawns under."""
    return server.token_env or _DEFAULT_STDIO_TOKEN_ENV


def _is_per_user_stdio(server: McpServerConfig) -> bool:
    """Whether a server is a per-user oauth server on the stdio transport (D4).

    Only these servers get the per-user subprocess pool: token-into-env injection, the
    pool caps, idle reaping, expiry/401 restart, and orphan cleanup. Every other server
    (plain stdio, http per-user, http/sse machine-identity) is untouched by all of it.
    """
    return server.transport == "stdio" and _is_per_user_credential(server)


def _call_window_lock_for(server: McpServerConfig, user_id: str | None) -> asyncio.Lock:
    """The call-window lock to serialize a server's product-dir diff window under (D2).

    A per-user oauth server descends to a per-(server, user) lock so two different users'
    concurrent calls do not serialize against each other; every other server keeps the
    single per-server ``_call_window_lock`` (behavior unchanged). Per-user locks are lazily
    created and held in a per-server map keyed by user_id.
    """
    if not _is_per_user_credential(server) or user_id is None:
        return server._call_window_lock
    return server._per_user_call_window_locks.setdefault(user_id, asyncio.Lock())


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


def _unavailable_result(server_id: str) -> str:
    """Tool-call result text when a server is degraded/unavailable (D5)."""
    return (
        f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' is temporarily unavailable "
        f"(connection lost; it will be retried on the next call)."
    )


def _auth_unavailable_result(server_id: str) -> str:
    """Tool-call result text when an oauth2 server's authentication is unavailable (D5)."""
    return (
        f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' authentication unavailable: re-authorize "
        f"or check the OAuth2 credentials."
    )


def _needs_authorization_result(server_id: str, *, delivered: bool) -> str:
    """Tool-call result text when a per-user oauth call has no token yet (Group 6, D8).

    Returned on the degrade chain (never raised): the user must authorize before this
    server can act on their behalf. The authorization link is delivered out-of-band via a
    private DM (never embedded here, since the result may surface in a shared channel), so
    the text only tells the user a link was sent — or, when no IM delivery path exists,
    that authorization is required.
    """
    if delivered:
        return (
            f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' needs your authorization. An "
            f"authorization link has been sent to you privately (DM) — open it to grant access, "
            f"then try again."
        )
    return (
        f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' needs your authorization before it can act "
        f"on your behalf. Please authorize this server, then try again."
    )


async def _emit_authorization_link(server: McpServerConfig, user_id: str, agent_id: str) -> bool:
    """Build + deliver a per-user authorization link for the triple (Group 6, D8).

    Thin indirection over :func:`authorization.emit_authorization_link` so call-tool sites
    trigger authorization without referencing the seam module directly (and so tests can
    patch this one symbol). Returns True iff the link was delivered (e.g. DM'd).
    """
    return await _authz.emit_authorization_link(server, user_id, agent_id)


async def _trigger_per_user_authorization(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> str:
    """Emit an authorization link and return the degrade-chain "needs authorization" text.

    Called when a per-user oauth call has no resolvable token. With a routable user_id the
    link is built + delivered (best-effort DM); without one (unroutable caller) no link can
    be addressed, so only the generic "authorization required" notice is returned.
    """
    if user_id is None:
        logger.info("mcp_per_user_no_user_id server_id=%s", server.id)
        return _needs_authorization_result(server.id, delivered=False)
    delivered = await _emit_authorization_link(server, user_id, agent_id or "")
    return _needs_authorization_result(server.id, delivered=delivered)


# === mcp-per-user-apikey (Group 2.5, D3): no-key degrade + credential-submission trigger ===
# Unlike per-user oauth, a per-user api-key has no refresh: the only question is whether the
# user's (user, agent, server) key is stored. A missing key returns a "needs credential"
# result on the same degrade chain and triggers submission per the server's ``credential_input``
# (secure form link for form/both; in-DM tool guidance for tool-only). The key never appears
# in the result text (it may surface in a shared channel).


def _has_user_credential(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> bool:
    """Whether the calling user already has a stored key for this per-user api-key triple."""
    if user_id is None:
        return False
    return resolve_user_token(server.id, user_id, agent_id) is not None


def _needs_credential_result(server_id: str, *, delivered: bool, tool_only: bool = False) -> str:
    """Tool-call result text when a per-user api-key call has no stored key (D3).

    Returned on the degrade chain (never raised). The actual key is supplied out-of-band
    (a DM'd secure form, or the in-DM ``set_mcp_credential`` tool) — never embedded here,
    since the result may surface in a shared channel.
    """
    if tool_only:
        return (
            f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' needs your api-key/credential. Send it "
            f"privately (DM) using the set_mcp_credential tool, then try again."
        )
    if delivered:
        return (
            f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' needs your api-key/credential. A secure "
            f"submission link has been sent to you privately (DM) — open it to provide your key, "
            f"then try again."
        )
    return (
        f"{_UNAVAILABLE_RESULT_PREFIX} '{server_id}' needs your api-key/credential before it can "
        f"act on your behalf. Please provide your key, then try again."
    )


async def _emit_credential_link(server: McpServerConfig, user_id: str, agent_id: str) -> bool:
    """Build + deliver a per-user credential-submission (secure form) link for the triple.

    Thin indirection over :func:`credential_submission.emit_credential_link` so call-tool
    sites trigger submission without referencing the seam module directly (and so tests can
    patch this one symbol). Returns True iff the link was delivered (e.g. DM'd).
    """
    from fleetent.integrations.mcp import credential_submission as _cred

    return await _cred.emit_credential_link(server, user_id, agent_id)


async def _trigger_per_user_credential(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> str:
    """Trigger credential submission and return the "needs credential" degrade text (D3).

    For ``credential_input`` form/both a secure-form link is built + DM'd (best-effort);
    for tool-only no form link is emitted and the user is guided to ``set_mcp_credential``
    in a DM. An unroutable caller (no user_id) gets only the generic notice.
    """
    if user_id is None:
        logger.info("mcp_per_user_no_user_id server_id=%s", server.id)
        return _needs_credential_result(server.id, delivered=False)
    if server.credential_input == "tool":
        return _needs_credential_result(server.id, delivered=False, tool_only=True)
    delivered = await _emit_credential_link(server, user_id, agent_id or "")
    return _needs_credential_result(server.id, delivered=delivered)


def find_registered_server(server_id: str, scope: int | None = None) -> McpServerConfig | None:
    """Return the registered config for ``(scope, server_id)``, or None when unknown.

    Public read of the live registry so out-of-band sites (the standalone OAuth callback /
    refresher) can resolve a server's OAuth config (token_url / client_id /
    client_secret_env / oauth_grant) by id without importing the private registry dict.
    """
    return _server_registry.get((scope, server_id))


# === mcp-per-user-oauth2 (Group 7, D7): transparent token refresh seam ===========
# An injectable async refresher ``(server_id, user_id, agent_id, token) -> UserToken | None``
# used to silently refresh an expired-but-refreshable access token before a per-user call,
# so the refresh is transparent to the caller (D7/7.3). standalone boot wires a refresher
# that calls ``oauth_authcode.refresh_token`` and writes the rotated token to the local
# store; managed (slice 2) may inject a different one. A None return means "could not
# refresh" (genuine auth failure) — the call then degrades to "needs authorization". The
# seam holds only a callable reference (no live resource, no agent→platform import).
TokenRefresher = Callable[[str, str, str | None, UserToken], "Awaitable[UserToken | None]"]

_token_refresher: TokenRefresher | None = None


def set_token_refresher(refresher: TokenRefresher | None) -> None:
    """Wire (or clear) the injected transparent token refresher (D7).

    Called once at agent boot (standalone) so an expired-but-refreshable token is refreshed
    in place before the call proceeds. Passing None disables transparent refresh (the call
    then degrades on the expired token, never crashing).
    """
    global _token_refresher
    _token_refresher = refresher


def get_token_refresher() -> TokenRefresher | None:
    """Return the wired transparent token refresher, or None when none is set."""
    return _token_refresher


def _token_is_expired(token: UserToken, *, now: float) -> bool:
    """Whether a token's access token has passed its expiry on the wall clock (D7).

    A token with no known ``expires_at`` is treated as live (never proactively refreshed):
    only an explicit expiry drives a transparent refresh.
    """
    return token.expires_at is not None and now >= token.expires_at


async def _ensure_fresh_user_token(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> bool:
    """Ensure the caller has a usable (refreshed if needed) per-user token (D7/7.3).

    Resolves the user's stored token; when it is expired and a refresh token is held, the
    wired refresher is invoked to rotate it in place (transparent to the caller) and the
    result is persisted by the refresher. Returns whether a usable token now exists:

    * no token at all → False (drives this user's authorization trigger);
    * live token (or expired but no refresher / no refresh token) → True (call proceeds;
      a stale-but-present token lets the resource end answer / degrade);
    * refresh failed genuinely (refresher returned None) → False (drives re-authorization).

    Never raises: a transient refresher error is contained so the call still proceeds on
    the existing token rather than crashing the agent loop.
    """
    if user_id is None:
        return False
    token = resolve_user_token(server.id, user_id, agent_id)
    if token is None:
        return False
    refresher = _token_refresher
    if (
        refresher is None
        or token.refresh_token is None
        or not _token_is_expired(token, now=time.time())
    ):
        return True
    try:
        refreshed = await refresher(server.id, user_id, agent_id, token)
    except Exception as exc:  # noqa: BLE001 — a transient refresh error must not crash the call
        logger.warning("mcp_token_refresh_failed server_id=%s error=%s", server.id, exc)
        return True  # keep the (stale) token; the call degrades downstream, never crashes
    # None = genuine auth failure (refresher cleared the bad token): re-authorization needed.
    return refreshed is not None


def _oauth_degraded_result(server: McpServerConfig, exc: BaseException) -> str | None:
    """Map an oauth2 error bubbling from a call to a degraded result, else None (D5).

    Genuine credential failure (sticky flag set by the provider, or OAuthAuthUnavailableError)
    → sticky "authentication unavailable". Transient SDK oauth/token errors (e.g. token
    endpoint 5xx) → "temporarily unavailable", retryable, NOT sticky. Never crashes the loop.
    """
    if server.auth_type != "oauth2":
        return None
    if server._auth_unavailable or isinstance(exc, OAuthAuthUnavailableError):
        server._auth_unavailable = True
        return _auth_unavailable_result(server.id)
    if isinstance(exc, (OAuthFlowError, OAuthTokenError)):
        logger.warning("mcp_oauth_transient server_id=%s error=%s", server.id, exc)
        return _unavailable_result(server.id)
    return None


async def _close_host(host: _SessionHost) -> None:
    """Signal a session host to close and await its teardown (best-effort, bounded).

    The host owns the transport's anyio cancel scope, so it must run its own teardown;
    we only wake it and wait. A teardown that hangs past the timeout is cancelled so
    shutdown stays bounded; any teardown error is the host's own (logged there) — this
    never raises.
    """
    host.close_event.set()
    try:
        await asyncio.wait_for(asyncio.shield(host.task), _HOST_CLOSE_TIMEOUT)
    except TimeoutError:
        host.task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.gather(host.task, return_exceptions=True)
    except Exception as exc:  # noqa: BLE001 — containment: a close failure never propagates
        logger.warning("mcp_host_close_failed error=%s", exc)


async def aclose_all() -> None:
    """Release every MCP session host on shutdown (best-effort, contained).

    Each host tears down its own transport (stdio subprocess / Streamable HTTP / SSE,
    incl. the HTTP DELETE handshake) inside its own task, so enter/exit stay on the same
    task. A single host failing or hanging MUST NOT block the others or change the
    process exit code.
    """
    hosts = list(_session_hosts.values())
    _session_hosts.clear()
    _active_sessions.clear()
    if hosts:
        await asyncio.gather(*(_close_host(h) for h in hosts), return_exceptions=True)


# === mcp-per-user-oauth2 (D4): per-user stdio subprocess pool lifecycle =======


def _is_per_user_stdio_key(key: SessionKey) -> bool:
    """Whether a live-session key belongs to a per-user oauth stdio host.

    The pool caps / reaper / orphan cleanup operate only on per-user stdio hosts; a
    3-tuple key whose registered server is per-user stdio identifies one. http per-user
    hosts (also 3-tuple) and every 2-tuple plain key are deliberately left out.
    """
    if len(key) != 3:
        return False
    server = _server_registry.get((key[0], key[1]))
    return server is not None and _is_per_user_stdio(server)


def _per_user_stdio_host_items() -> list[tuple[SessionKey, _SessionHost]]:
    """All live (key, host) pairs that are per-user oauth stdio hosts."""
    return [(k, h) for k, h in _session_hosts.items() if _is_per_user_stdio_key(k)]


async def _evict_host(key: SessionKey, reason: str) -> None:
    """Drop one host from the pool and tear it down on its own owner task (logged).

    The host owns its transport's cancel scope, so eviction is a close-signal (via
    ``_close_host``) — never a cross-task unwind. Always logged so a cap-driven drop is
    never silent. Removing the registry handle first makes the slot immediately reusable.
    """
    host = _session_hosts.pop(key, None)
    _active_sessions.pop(key, None)
    if host is None:
        return
    logger.warning("mcp_stdio_evict key=%r reason=%s", key, reason)
    await _close_host(host)


async def _enforce_stdio_caps(server: McpServerConfig, user_id: str | None) -> None:
    """Evict LRU per-user stdio host(s) so spawning one more honors the pool caps (D4).

    Enforces the per-user cap first (LRU among the same user's hosts), then the global
    total cap (LRU across all per-user stdio hosts). Eviction frees one slot for the
    impending spawn; each drop is logged (never silent). Only per-user stdio hosts are
    counted — plain/http hosts are exempt.
    """
    items = _per_user_stdio_host_items()
    # Per-user cap: count this user's live hosts; evict the oldest until one slot is free.
    user_items = sorted(
        (it for it in items if it[1].user_id == user_id), key=lambda it: it[1].last_used
    )
    while len(user_items) >= _STDIO_MAX_PER_USER:
        key, _ = user_items.pop(0)
        await _evict_host(key, "per_user_cap")
    # Total cap: recount (eviction may have changed the set) and evict global LRU.
    items = sorted(_per_user_stdio_host_items(), key=lambda it: it[1].last_used)
    while len(items) >= _STDIO_MAX_TOTAL:
        key, _ = items.pop(0)
        await _evict_host(key, "total_cap")


async def _reap_idle_stdio_hosts() -> None:
    """Reap per-user stdio hosts idle past the timeout (background reaper sweep, D4).

    A host is reaped by signaling its owner task to close (``_close_host``) — the owner
    task runs its own teardown so enter/exit stay on the same task (no cross-task unwind).
    Best-effort and contained: a single reap failure never aborts the sweep.
    """
    now = _stdio_clock()
    stale = [k for k, h in _per_user_stdio_host_items() if now - h.last_used >= _STDIO_IDLE_TIMEOUT]
    for key in stale:
        await _evict_host(key, "idle_timeout")


async def cleanup_orphan_stdio_hosts() -> None:
    """Tear down every per-user stdio host (orphan-cleanup hook, D4).

    Wired into agent shutdown / abnormal-exit cleanup so per-user subprocesses do not
    outlive the agent. Each host closes on its own owner task; failures are contained so
    one stuck subprocess never blocks the rest or changes the exit code.
    """
    keys = [k for k, _ in _per_user_stdio_host_items()]
    for key in keys:
        await _evict_host(key, "orphan_cleanup")


_stdio_reaper_task: asyncio.Task[None] | None = None


async def _stdio_reaper_loop() -> None:
    """Periodic reaper loop: sweep idle per-user stdio hosts on the reap interval."""
    while True:
        await asyncio.sleep(_STDIO_REAP_INTERVAL)
        try:
            await _reap_idle_stdio_hosts()
        except Exception as exc:  # noqa: BLE001 — a sweep failure must not kill the reaper
            logger.warning("mcp_stdio_reap_failed error=%s", exc)


def start_stdio_reaper() -> None:
    """Start the background idle-reaper task (idempotent); wired at agent boot."""
    global _stdio_reaper_task
    if _stdio_reaper_task is not None and not _stdio_reaper_task.done():
        return
    _stdio_reaper_task = asyncio.ensure_future(_stdio_reaper_loop())


async def stop_stdio_reaper() -> None:
    """Stop the background reaper task (best-effort, bounded); wired at shutdown."""
    global _stdio_reaper_task
    task = _stdio_reaper_task
    _stdio_reaper_task = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(BaseException):
        await asyncio.gather(task, return_exceptions=True)


async def register_all(
    servers: list[McpServerConfig],
    scope: int | None = None,
    agent_home: Path | None = None,
    tool_naming: Any = "claude",
) -> None:
    global _projector
    _projector = make_projector(tool_naming)  # active projection for this registration
    _failed_strict_servers.clear()  # recompute startup-failed strict set each registration
    for server in servers:
        try:
            await _register_server(server, scope, agent_home)
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


async def _register_server(
    server: McpServerConfig, scope: int | None = None, agent_home: Path | None = None
) -> None:
    server._agent_scope = scope
    server._agent_home = agent_home
    # approval-boundary-redesign D4: install this server's approval rules into the central
    # policy so MCP calls matching a rule are gated (default no-approval otherwise).
    from fleetent.governance import approval_policy

    approval_policy.set_server_mcp_rules(server.id, server.approval_rules)
    # unified-file-exchange: bind the /exchange effective root so the fence + result
    # rewrite can resolve this server's products (no-op for non-stdio / no agent_home).
    _bind_exchange_root(server, agent_home)
    if server.auth_type == "oauth2":
        _clear_oauth_auth_state(server)  # (re-)registration clears sticky auth state (D5)
    # All transports go through one SDK-ClientSession path (stdio / http / sse).
    await _register_session_server(server, scope)


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


def _resolve_env_ref(value: str) -> str:
    """Resolve an ``env:VAR_NAME`` reference from the parent process environment.

    Values prefixed with ``env:`` are looked up in ``os.environ`` (populated by the agent
    `.env` via ``load_dotenv``), returning an empty string when the var is unset. Any other
    value is returned verbatim. This lets secrets live in `.env` rather than inline in
    ``agent.yaml`` — used for both stdio env values and HTTP header values.
    """
    if value.startswith("env:"):
        return os.environ.get(value[4:], "")
    return value


def _convention_cwd(server: McpServerConfig, agent_home: Path) -> Path:
    """The partition-tree root a stdio MCP server runs in (unified-file-exchange)."""
    return agent_home / "exchange" / server.id


def _convention_env(server: McpServerConfig, agent_home: Path) -> dict[str, str]:
    """The convention-injected XDG triple pointing at the server's partition tree.

    ``data/`` is the artifact root that maps to ``/exchange/<server_id>`` (enters the
    namespace); ``config/`` and ``cache/`` are isolated outside it (silences ledger
    noise from a server's settings/cache writes).
    """
    base = _convention_cwd(server, agent_home)
    return {
        "XDG_DATA_HOME": str(base / "data"),
        "XDG_CONFIG_HOME": str(base / "config"),
        "XDG_CACHE_HOME": str(base / "cache"),
    }


def _subprocess_env(
    server: McpServerConfig,
    agent_home: Path | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, str]:
    """Environment for a stdio MCP subprocess (mcp-stdio-isolation).

    Merge order is safe host whitelist < convention injection < explicitly declared env <
    per-user oauth token. The convention layer (unified-file-exchange) points the server's
    XDG dirs at its ``<agent_home>/exchange/<id>`` partition tree so its products land in
    the addressable ``/exchange`` namespace; an explicitly configured XDG is adopted in
    place (it wins). ``file_isolation: "off"`` or a missing ``agent_home`` skips the
    convention (the latter keeps legacy call sites byte-identical). The full platform
    environment is never inherited; ``env:VAR_NAME`` values resolve from the parent
    process environment.

    For a per-user oauth stdio server (mcp-per-user-oauth2 D4) the calling user's *current*
    access token is injected under ``token_env`` (or the default name) at spawn so the
    subprocess authenticates as that user; refresh is by re-spawn, never in-place mutation.
    Every other server gets no token var at all, so its env stays byte-identical.
    """
    resolved = {k: _resolve_env_ref(v) for k, v in server.env.items()}
    convention = (
        _convention_env(server, agent_home)
        if agent_home is not None and server.file_isolation != "off"
        else {}
    )
    env = {**_safe_base_env(), **convention, **resolved}
    if _is_per_user_stdio(server) and user_id is not None:
        token = resolve_user_token(server.id, user_id, agent_id)
        if token is not None and token.access_token:
            env[_stdio_token_env_name(server)] = token.access_token
    return env


def _convention_applies(server: McpServerConfig, agent_home: Path | None) -> bool:
    """Whether the /exchange convention (cwd + XDG injection + root binding) applies."""
    return agent_home is not None and server.file_isolation != "off"


def _stdio_params(
    server: McpServerConfig, user_id: str | None = None, agent_id: str | None = None
) -> StdioServerParameters:
    """Build the stdio subprocess parameters, applying the /exchange convention.

    When the server carries an `_agent_home` (set at registration) and isolation is on,
    the subprocess runs in its partition root `<agent_home>/exchange/<id>` (created here
    so the spawn never fails on a missing cwd) with the convention XDG triple injected.
    Otherwise the legacy params (no cwd, no convention) are produced byte-identically.

    ``user_id`` / ``agent_id`` drive the per-user oauth token-into-env injection (D4) and
    are ignored (no token var) for every non-per-user-oauth stdio server.
    """
    agent_home = server._agent_home
    cwd: str | None = None
    if _convention_applies(server, agent_home):
        assert agent_home is not None
        cwd_path = _convention_cwd(server, agent_home)
        cwd_path.mkdir(parents=True, exist_ok=True)
        cwd = str(cwd_path)
    return StdioServerParameters(
        command=server.command,
        args=server.args,
        env=_subprocess_env(server, agent_home, user_id, agent_id),
        cwd=cwd,
    )


def _bind_exchange_root(server: McpServerConfig, agent_home: Path | None) -> None:
    """Bind this stdio server's effective file root so `/exchange/<id>` resolves.

    No-op for non-stdio servers, when no agent_home is supplied, or when the server opts
    out (`file_isolation: off`). Idempotent — re-registration rebinds the same root.
    """
    if server.transport != "stdio" or not _convention_applies(server, agent_home):
        return
    assert agent_home is not None
    from fleetent import artifact_exchange

    artifact_exchange.register_server_root(
        server.id, artifact_exchange.effective_root(server, agent_home)
    )


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
        _forget_tool_identity(name)
    for tool_def in tools:
        _register_tool(server, _make_tool_name(server.id, tool_def.name), tool_def, scope)
    _register_utility_tools(server, scope)


async def _refresh_stdio_tools(server: McpServerConfig, scope: int | None, session: Any) -> None:
    """Re-list and re-register a stdio server's tools after a list_changed notification.

    Identity-guarded (ignores a notification from a session that has since been replaced)
    and deduped via a per-server lock (coalesces a burst of notifications). Tools are
    user-agnostic, so the refresh tracks the registration-time (user_id=None) session slot.
    """
    refresh_key = _session_key(server, scope, None)
    if _active_sessions.get(refresh_key) is not session:
        return
    if server._list_refresh_lock.locked():
        return
    async with server._list_refresh_lock:
        if _active_sessions.get(refresh_key) is not session:
            return
        try:
            tools = await _list_all_tools(session)
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
        # Tools are user-agnostic; track the registration-time (user_id=None) session slot.
        current = _active_sessions.get(_session_key(server, scope, None))
        if current is not None:
            asyncio.create_task(_refresh_stdio_tools(server, scope, current))

    return handler


async def _http_headers(server: McpServerConfig) -> dict[str, str]:
    """Build request headers for an http/sse transport: custom headers (with env: refs
    resolved) plus an Authorization Bearer when a token is available.

    Accept negotiation, Mcp-Session-Id and the MCP-Protocol-Version header are NOT set
    here — the SDK transport / ClientSession owns them.
    """
    headers: dict[str, str] = {}
    if server.headers:
        headers.update({k: _resolve_env_ref(v) for k, v in server.headers.items()})
    # The oauth2 Bearer rides the transport `auth=` (per-request, refreshable); only the
    # static api_key Bearer is baked into the session headers here.
    if server.auth_type == "api_key" and server.api_key_env:
        key = os.environ.get(server.api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    return headers


class _PerUserBearerAuth(httpx.Auth):
    """httpx.Auth that injects the calling user's *current* OAuth bearer per request (D3).

    Holds a ``token_getter`` callable bound to one ``(server, user, agent)`` triple and
    reads it on every request in ``auth_flow``, so a token refreshed in the store between
    requests is picked up by the next request transparently — no ClientSession rebuild.
    When the getter returns None (no token) no Authorization header is set, leaving the
    resource end to answer 401 / drive the degrade path rather than sending a stale bearer.
    """

    def __init__(
        self, token_getter: Callable[[], str | None], header_style: str = "bearer"
    ) -> None:
        self._token_getter = token_getter
        self._header_style = header_style

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        token = self._token_getter()
        if token:
            if self._header_style == "x_api_key":
                request.headers["X-API-Key"] = token
            else:
                request.headers["Authorization"] = f"Bearer {token}"
        yield request


def _per_user_token_getter(
    server_id: str, user_id: str, agent_id: str | None
) -> Callable[[], str | None]:
    """Build a token getter closing over ``(server_id, user_id, agent_id)`` (D3).

    The returned callable resolves the user's *current* access token from the per-user
    token store on each invocation (None when none is stored). This group does NOT refresh
    or write tokens (that is Group 7); the getter only reflects what the store holds now,
    which is exactly what makes refresh transparent to the live session.
    """

    def getter() -> str | None:
        token = resolve_user_token(server_id, user_id, agent_id)
        return token.access_token if token is not None else None

    return getter


def _http_auth(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> httpx.Auth | None:
    """The httpx.Auth bound to a server's http(s) client.

    A per-user oauth server (authorization_code) gets a ``_PerUserBearerAuth`` bound to the
    calling user, injecting that user's current token per request. Every other server keeps
    the historical auth: the SDK client_credentials provider for oauth2, None otherwise.
    """
    if _is_per_user_credential(server):
        if user_id is None:
            return None  # unroutable; caller short-circuits before reaching here
        # per-user oauth always Bearer; per-user api-key follows the server's header_style.
        header_style = server.header_style if _is_per_user_apikey(server) else "bearer"
        return _PerUserBearerAuth(
            _per_user_token_getter(server.id, user_id, agent_id), header_style=header_style
        )
    return _oauth_auth(server)


def _build_http_client(
    server: McpServerConfig,
    headers: dict[str, str],
    user_id: str | None,
    agent_id: str | None,
) -> httpx.AsyncClient:
    """Build the httpx.AsyncClient fed to the new streamable-http transport (D3).

    Uses the SDK's ``create_mcp_http_client`` so the MCP defaults (follow_redirects, the
    timeout shape) match the legacy transport exactly. Per-server timeouts map as before:
    connect_timeout → the connection/request timeout, call_timeout → the streamed read.
    The auth handler is per-user for a per-user oauth server, else the historical auth.
    """
    timeout = httpx.Timeout(server.connect_timeout, read=server.call_timeout)
    return create_mcp_http_client(
        headers=headers or None,
        timeout=timeout,
        auth=_http_auth(server, user_id, agent_id),
    )


def _transport_cm(
    server: McpServerConfig,
    headers: dict[str, str],
    user_id: str | None = None,
    agent_id: str | None = None,
) -> Any:
    """Return the SDK transport context manager for the server's transport.

    All three SDK clients yield a stream tuple whose first two items are the
    (read, write) streams fed to a ClientSession. The http path uses the non-deprecated
    ``streamable_http_client(url, http_client=...)`` for both per-user and plain servers:
    per-user binds a ``_PerUserBearerAuth`` over ``(server, user, agent)``, plain servers
    build an equivalent client from the existing headers/auth so their behavior is unchanged.
    """
    if server.transport == "stdio":
        return stdio_client(_stdio_params(server, user_id, agent_id))
    # Per-server timeouts map onto the SDK transport: connect_timeout governs the
    # connection / request POST (`timeout`), call_timeout the streamed tool-result read
    # (`sse_read_timeout`) — the long-lived session means both are set once, at open.
    if server.transport == "sse":
        return sse_client(
            server.url,
            headers=headers,
            timeout=server.connect_timeout,
            sse_read_timeout=server.call_timeout,
            auth=_oauth_auth(server),
        )
    # default: streamable http on the non-deprecated API. A plain server routes through the
    # legacy `streamablehttp_client` shim (preserves any external monkeypatch / behavior);
    # a per-user credential server (oauth OR dynamic api-key) builds its user-bound client and
    # uses the new API directly so the per-user auth (Bearer / X-API-Key per header_style) is
    # attached without round-tripping the legacy headers/auth kwargs.
    if _is_per_user_credential(server):
        http_client = _build_http_client(server, headers, user_id, agent_id)
        return streamable_http_client(server.url, http_client=http_client)
    return streamablehttp_client(
        server.url,
        headers=headers,
        timeout=server.connect_timeout,
        sse_read_timeout=server.call_timeout,
        auth=_oauth_auth(server),
    )


def streamablehttp_client(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    sse_read_timeout: float = 300.0,
    auth: httpx.Auth | None = None,
) -> Any:
    """Re-export shim for the deprecated `streamablehttp_client(headers=,auth=)` entry (D3).

    The SDK deprecated the headers/timeout/auth kwargs in favor of
    ``streamable_http_client(url, http_client=...)``. This wrapper keeps the legacy
    signature usable (for existing call sites / tests) while internally building an
    ``httpx.AsyncClient`` from those kwargs and delegating to the non-deprecated API — so
    non-per-user http behavior is unchanged but rides the new transport underneath.
    """
    client = create_mcp_http_client(
        headers=headers or None,
        timeout=httpx.Timeout(timeout, read=sse_read_timeout),
        auth=auth,
    )
    return streamable_http_client(url, http_client=client)


@dataclass
class _SessionHost:
    """Owns one MCP ClientSession's lifecycle in a dedicated task.

    The transport + ClientSession context managers are entered and exited inside
    ``task`` only; other tasks interact through ``session`` (consume) and ``close_event``
    (request teardown), never by entering/exiting the contexts themselves.

    The pool-bookkeeping fields are only meaningful for a per-user oauth stdio host
    (mcp-per-user-oauth2 D4): ``last_used`` drives idle reaping + LRU eviction,
    ``token_expires_at`` bounds the subprocess lifetime to its token's validity, and
    ``user_id`` keys the per-user cap. They are inert for every other host.
    """

    task: asyncio.Task[None]
    close_event: asyncio.Event
    session: Any = None
    last_used: float = 0.0
    token_expires_at: float | None = None
    user_id: str | None = None


async def _host_session(
    server: McpServerConfig,
    scope: int | None,
    headers: dict[str, str],
    ready: asyncio.Future,
    close_event: asyncio.Event,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Session owner coroutine: enter transport + ClientSession, init, park, exit — same task.

    On a successful open it resolves ``ready`` with the live session and parks on
    ``close_event``; on an open failure it propagates the error through ``ready``. A
    teardown error (exit phase) is the host's own and is logged, never propagated — the
    process must not die because one connector failed to close (2026-06-11). ``user_id`` /
    ``agent_id`` bind the http transport's per-user bearer auth (ignored for non-per-user
    servers); the per-user httpx.AsyncClient is entered/exited in this owner task only.
    """
    try:
        async with _transport_cm(server, headers, user_id, agent_id) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(
                read, write, message_handler=_make_message_handler(server, scope)
            ) as session:
                init_result = await session.initialize()
                _capture_init_result(server, _init_result_to_dict(init_result))
                if not ready.done():
                    ready.set_result(session)
                await close_event.wait()
    except Exception as exc:  # noqa: BLE001 — open failure → caller; teardown failure → log
        if not ready.done():
            ready.set_exception(exc)
        else:
            logger.warning("mcp_session_teardown_failed server_id=%s error=%s", server.id, exc)


async def _open_session_for(
    server: McpServerConfig,
    scope: int | None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> Any:
    """Open a transport-specific ClientSession owned by a dedicated host task, initialized.

    Unified across stdio / http / sse: the SDK owns the wire; the host task holds the
    transport + ClientSession contexts (entered/exited in that one task). The live
    ClientSession is stored in _active_sessions[key] for reuse and lazy reconnect; its host
    in _session_hosts[key] for lifecycle. ``user_id`` selects the per-user session slot for
    a per-user oauth server (ignored — keyed under None — for every other server) and, with
    ``agent_id``, binds that user's per-request bearer auth on the http transport.
    """
    key = _session_key(server, scope, user_id)
    # Per-user oauth stdio only: honor the pool caps before spawning a new subprocess, so a
    # new user/server cannot push the live count past the global / per-user limit. Eviction
    # closes the LRU host(s) on their own owner task (signal, never cross-task unwind) and
    # logs — never a silent drop. Reusing an existing key (same user) is not a new spawn.
    if _is_per_user_stdio(server) and key not in _session_hosts:
        await _enforce_stdio_caps(server, user_id)
    headers = {} if server.transport == "stdio" else await _http_headers(server)
    loop = asyncio.get_event_loop()
    ready: asyncio.Future = loop.create_future()
    close_event = asyncio.Event()
    task = asyncio.ensure_future(
        _host_session(server, scope, headers, ready, close_event, user_id, agent_id)
    )
    try:
        session = await asyncio.wait_for(ready, server.connect_timeout)
    except (Exception, asyncio.CancelledError):
        # Open failed/timed out: tear the host down so no orphan task/connection leaks.
        close_event.set()
        task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.gather(task, return_exceptions=True)
        raise
    now = _stdio_clock()
    token_expiry = _stdio_token_expiry(server, user_id, agent_id)
    _session_hosts[key] = _SessionHost(
        task=task,
        close_event=close_event,
        session=session,
        last_used=now,
        token_expires_at=token_expiry,
        user_id=user_id,
    )
    _active_sessions[key] = session
    return session


def _stdio_token_expiry(
    server: McpServerConfig, user_id: str | None, agent_id: str | None
) -> float | None:
    """Absolute expiry to bound a per-user stdio host's lifetime, else None (D4).

    Reads the token the subprocess just spawned with so the pool can pre-empt a call once
    that token has expired (re-spawn with a refreshed token). None for every non-per-user
    stdio host (no lifetime bound) or when the token carries no expiry.
    """
    if not _is_per_user_stdio(server) or user_id is None:
        return None
    token = resolve_user_token(server.id, user_id, agent_id)
    return token.expires_at if token is not None else None


async def _register_session_server(server: McpServerConfig, scope: int | None = None) -> None:
    """Register a server (any transport) via a held SDK ClientSession."""
    session = await _open_session_for(server, scope)
    _server_registry[(scope, server.id)] = server

    tools = await _list_all_tools(session)
    for tool_def in tools:
        tool_name = _make_tool_name(server.id, tool_def.name)
        _register_tool(server, tool_name, tool_def, scope)

    logger.info(
        "mcp_server_registered server_id=%s transport=%s tool_count=%d",
        server.id,
        server.transport,
        len(tools),
    )
    _register_utility_tools(server, scope)


# Protocol version sourced from the official SDK (auto-tracks; no hand-pinned literal).
# The SDK ClientSession negotiates the version and echoes the MCP-Protocol-Version header
# internally; this constant is only the fallback used by _capture_init_result when a
# server omits a version.
PROTOCOL_VERSION = LATEST_PROTOCOL_VERSION
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


def _clear_oauth_auth_state(server: McpServerConfig) -> None:
    """Clear sticky auth-unavailable flag and cached token (D5 recovery trigger).

    Called on (re-)registration / config reload so updated credentials take effect on the
    next resolve. Recovery is by this explicit signal, not by timed backoff.
    """
    server._auth_unavailable = False


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


def _oauth_auth(server: McpServerConfig) -> httpx.Auth | None:
    """The httpx.Auth handed to the SDK transport: the official client_credentials provider
    for oauth2 (SDK-maintained token acquisition/refresh + RFC 8707), None otherwise."""
    if server.auth_type == "oauth2":
        return _FleetentClientCredentialsProvider(server)
    return None


class _FleetentTokenStorage:
    """Minimal in-memory TokenStorage for the SDK oauth2 provider (structural Protocol).

    Per provider/session instance — token caching holds for the session lifetime; a fresh
    session (reopen) starts cold (see decisions.md D6).
    """

    def __init__(self) -> None:
        self._tokens: SdkOAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> SdkOAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: SdkOAuthToken) -> None:
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


class _FleetentClientCredentialsProvider(ClientCredentialsOAuthProvider):
    """fleetent adapter over the SDK's client_credentials provider.

    Maps McpServerConfig onto the SDK provider, preseeds the authorization-server metadata
    from the explicit ``token_url`` (so the token endpoint works without requiring server
    ``.well-known`` discovery — discovery still wins if the server exposes it), and splits
    genuine credential errors (sticky auth-unavailable) from transient ones (retryable).
    See decisions.md D2/D3/D4.
    """

    def __init__(self, server: McpServerConfig) -> None:
        secret = os.environ.get(server.client_secret_env, "") if server.client_secret_env else ""
        super().__init__(
            server_url=server.url,
            storage=_FleetentTokenStorage(),
            client_id=server.client_id,
            client_secret=secret,
            token_endpoint_auth_method="client_secret_post",
            scopes=server.scope or None,
        )
        self._server = server
        self._token_url = server.token_url

    async def _initialize(self) -> None:
        await super()._initialize()
        if self._token_url:
            parsed = urlparse(self._token_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            # Preseed the AS metadata so _get_token_endpoint() resolves to the explicit
            # token_url without a .well-known round-trip. issuer/authorization_endpoint are
            # required by the model but unused for client_credentials.
            self.context.oauth_metadata = OAuthMetadata(
                issuer=base,  # type: ignore[arg-type]
                authorization_endpoint=urljoin(base, "/authorize"),  # type: ignore[arg-type]
                token_endpoint=self._token_url,  # type: ignore[arg-type]
            )

    async def _handle_token_response(self, response: httpx.Response) -> None:
        if _is_auth_error_response(response):
            self._server._auth_unavailable = True  # sticky: bad credentials, do not retry
            raise OAuthAuthUnavailableError(
                f"OAuth2 authentication unavailable for server '{self._server.id}': token "
                f"endpoint rejected the credentials (status={response.status_code}). "
                f"Re-authorize or check the OAuth2 credentials."
            )
        # Transient (5xx / non-credential 4xx): let the SDK raise OAuthTokenError (retryable).
        await super()._handle_token_response(response)


async def _list_all_tools(session: Any) -> list[Any]:
    """Fetch every page of `session.list_tools()`, following nextCursor, bounded by
    _MAX_TOOL_PAGES. Works for any transport (all go through the SDK ClientSession)."""
    tools: list[Any] = []
    cursor: str | None = None
    for _ in range(_MAX_TOOL_PAGES):
        result = await session.list_tools(cursor=cursor)
        tools.extend(result.tools or [])
        cursor = getattr(result, "nextCursor", None)
        if not cursor:
            return tools
    logger.warning("mcp_tools_list_page_cap cap=%d", _MAX_TOOL_PAGES)
    return tools


async def probe_server(server: McpServerConfig) -> dict[str, Any]:
    """One-shot connectivity check for the admin "Test" action.

    Opens a throwaway SDK ClientSession (any transport), runs the initialize handshake,
    lists tools — then discards the connection. Never touches the shared registry /
    AsyncExitStack / _active_sessions, so it is safe to run against an unregistered or
    candidate config. Returns connected/tool_count/tools, or connected=False + error.
    """
    try:
        headers = {} if server.transport == "stdio" else await _http_headers(server)
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(_transport_cm(server, headers))
            session: Any = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            tool_defs = await _list_all_tools(session)
        tools = [{"name": t.name, "description": t.description or ""} for t in tool_defs]
    except Exception as exc:  # noqa: BLE001 — surface any failure as a clean result
        return {"connected": False, "error": str(exc)}
    return {"connected": True, "tool_count": len(tools), "tools": tools}


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
            _forget_tool_identity(name)
    _server_registry.pop((scope, server_id), None)
    # A per-user oauth server holds one session/host per user (keys (scope, server_id, *));
    # drop every matching slot, not just the None one, so no per-user host is orphaned.
    keys = [k for k in _active_sessions if k[0] == scope and k[1] == server_id]
    for k in keys:
        _active_sessions.pop(k, None)
    host_keys = [k for k in _session_hosts if k[0] == scope and k[1] == server_id]
    for k in host_keys:
        # Sync context: wake each host so it tears itself down on its own task (no await
        # here); the host self-removes nothing else, so drop our handle too.
        host = _session_hosts.pop(k, None)
        if host is not None:
            host.close_event.set()


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


def _register_tool(
    server: McpServerConfig, tool_name: str, tool_def: Any, scope: int | None = None
) -> None:
    """Register one MCP tool. tool_def is an SDK Tool object (all transports go through
    the SDK ClientSession now), so name/description/inputSchema are attribute access."""
    import fleetent.tools.registry as tr

    # Record canonical identity + projection (mcp-tool-name-projection) so the LLM boundary
    # can present a projected name and resolve calls back to (server, raw_tool).
    _record_tool_identity(tool_name, server.id, str(getattr(tool_def, "name", "")))

    input_schema = _sanitize_input_schema(getattr(tool_def, "inputSchema", None))

    async def call(tool_context: Any = None, **kwargs: object) -> str:
        # tool_context binds to this param (never into kwargs → never leaks to MCP args).
        # It carries the run's scope_key for /exchange attribution (global-scope path; the
        # agent-scoped path threads the same via dispatch → call_tool).
        scope_key = getattr(tool_context, "scope_key", None)
        session_id = getattr(tool_context, "session_id", None)
        principal = getattr(tool_context, "principal", None)
        user_id = getattr(principal, "user_id", None)
        # agent_name completes the per-user oauth token isolation triple (Group 6, D1). The
        # authorization-link DM deliverer (Group 6, D8) is bound at the dispatch site (the
        # IM/outbound layer), so the MCP client never imports outbound here.
        agent_id = getattr(tool_context, "agent_name", None)
        return await _call_via_session(
            server.id,
            tool_def.name,
            dict(kwargs),
            server._agent_scope,
            scope_key=scope_key,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
        )

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


async def _reopen_session(
    server: McpServerConfig,
    scope: int | None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> Any | None:
    """Lazily re-open a dropped ClientSession (any transport) once. Returns the new
    session, or None if reopen failed. Closes the prior host first (no leak), then
    replaces the server's _active_sessions / _session_hosts entry. ``user_id`` targets the
    per-user session slot for a per-user oauth server (None slot for every other server);
    ``agent_id`` completes the per-user token isolation triple at (re)spawn time."""
    key = _session_key(server, scope, user_id)
    old = _session_hosts.pop(key, None)
    _active_sessions.pop(key, None)
    if old is not None:
        await _close_host(old)  # best-effort; a stuck/erroring old host never blocks reopen
    try:
        return await _open_session_for(server, scope, user_id, agent_id)
    except Exception as exc:  # noqa: BLE001 — reopen failure → caller marks unavailable
        logger.warning("mcp_reopen_failed server_id=%s error=%s", server.id, exc)
        return None


def _is_401_error(exc: BaseException) -> bool:
    """Whether an exception is an HTTP 401 (Unauthorized) — the token-rejected signal (D4)."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401


def _stdio_token_expired(server: McpServerConfig, key: SessionKey) -> bool:
    """Whether a per-user stdio host's spawn token has passed its expiry (D4).

    A subprocess authenticates with the token baked into its env at spawn; once that token
    expires the subprocess is stale and MUST be re-spawned with a refreshed token. False
    for any non-per-user-stdio host or a host with no known expiry.
    """
    if not _is_per_user_stdio(server):
        return False
    host = _session_hosts.get(key)
    if host is None or host.token_expires_at is None:
        return False
    return _stdio_clock() >= host.token_expires_at


async def _restart_stdio_for_fresh_token(
    server: McpServerConfig, scope: int | None, user_id: str | None, agent_id: str | None
) -> Any | None:
    """Re-spawn a per-user stdio subprocess so it picks up the store's *current* token (D4).

    Closes the stale host on its owner task and re-opens, re-resolving the token at spawn
    (the store may already hold a refreshed token from Group 6/7's refresh; if it does not,
    the new subprocess simply spawns with whatever the store currently holds and the call
    degrades downstream). Returns the new session, or None when the re-spawn failed.
    """
    key = _session_key(server, scope, user_id)
    old = _session_hosts.pop(key, None)
    _active_sessions.pop(key, None)
    if old is not None:
        await _close_host(old)
    try:
        return await _open_session_for(server, scope, user_id, agent_id)
    except Exception as exc:  # noqa: BLE001 — re-spawn failure → caller degrades
        logger.warning("mcp_stdio_restart_failed server_id=%s error=%s", server.id, exc)
        return None


def _touch_host(key: SessionKey) -> None:
    """Mark a host as just used (drives idle reaping + LRU eviction); no-op if absent."""
    host = _session_hosts.get(key)
    if host is not None:
        host.last_used = _stdio_clock()


def _result_to_text(result: Any) -> str:
    """Normalize an SDK CallToolResult into the agent-facing text (base64 never inlined)."""
    return _normalize_tool_result(
        getattr(result, "content", None),
        structured_content=getattr(result, "structuredContent", None),
        is_error=bool(getattr(result, "isError", False)),
    )


def _rewrite_result_paths(
    server_id: str,
    text: str,
    scope_key: str | None,
    session_id: str | None,
    user_id: str | None,
) -> str:
    """Apply the deterministic /exchange chokepoint rewrite to a tool result (best-effort).

    Delegates to artifact_exchange; a failure must never break the tool call (the agent
    still gets the raw result). No-op when no scope_key/root (byte-identical legacy).
    """
    try:
        from fleetent import artifact_exchange

        return artifact_exchange.rewrite_and_register(
            server_id, text, scope_key, session_id=session_id, user_id=user_id
        )
    except Exception as exc:  # noqa: BLE001 — attribution is auxiliary, never crash the call
        logger.warning("mcp_result_rewrite_failed server_id=%s error=%s", server_id, exc)
        return text


# Container mount point for the run's workspace; a stdio MCP server is a host process in a
# mount namespace where this path does not exist, so /workspace args are translated to the
# host bind-mount source before the call (the symmetric input side of the result rewrite).
_WORKSPACE_PREFIX = "/workspace"


def _translate_workspace_arg(value: str, host_dir: Path) -> str:
    """Rewrite a container workspace path to its host path.

    Absolute ``/workspace[/<rel>]`` is a deterministic prefix and always rewrites. A
    workspace-relative ref (e.g. the image-gen ``generated/<uuid>.png`` the model often
    passes verbatim, without the ``/workspace/`` prefix) rewrites ONLY when it resolves to
    a real file inside the workspace — existence + containment disambiguate it from
    ordinary string args (subject, body) and block ``..`` escapes.
    """
    if value == _WORKSPACE_PREFIX:
        return str(host_dir)
    if value.startswith(_WORKSPACE_PREFIX + "/"):
        return str(host_dir / value[len(_WORKSPACE_PREFIX) + 1 :])
    if value and not value.startswith("/") and "\n" not in value:
        base = os.path.normpath(str(host_dir))
        candidate = os.path.normpath(os.path.join(base, value))
        if (candidate == base or candidate.startswith(base + os.sep)) and os.path.isfile(candidate):
            return candidate
    return value


def _translate_workspace_args(args: Any, host_dir: Path) -> Any:
    """Recursively rewrite ``/workspace`` paths in tool args to host paths (stdio only).

    Non-string leaves and non-``/workspace`` strings pass through unchanged.
    """
    if isinstance(args, str):
        return _translate_workspace_arg(args, host_dir)
    if isinstance(args, dict):
        return {k: _translate_workspace_args(v, host_dir) for k, v in args.items()}
    if isinstance(args, list):
        return [_translate_workspace_args(v, host_dir) for v in args]
    return args


async def _call_via_session(
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    scope: int | None = None,
    *,
    scope_key: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Invoke a tool, then apply the call-window diff fallback when attributing (D2).

    Thin wrapper over `_call_via_session_inner` (which owns the SDK call + lazy-reconnect
    retry + the deterministic result rewrite). When a `scope_key` is threaded and the
    server has a registered product root, snapshot it before the call and diff-register
    any new files the rewrite missed — all under the server's per-call window lock so
    concurrent calls don't mis-attribute. The diff is best-effort and never affects the
    returned result; without attribution this is a byte-identical pass-through.
    """
    from fleetent import artifact_exchange

    server = _server_registry.get((scope, server_id))
    root = artifact_exchange.server_root(server_id) if (server is not None and scope_key) else None
    if root is None:
        return await _call_via_session_inner(
            server_id,
            tool_name,
            args,
            scope,
            scope_key=scope_key,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
        )
    assert server is not None

    async with _call_window_lock_for(server, user_id):
        before = artifact_exchange.snapshot_products(root)
        text = await _call_via_session_inner(
            server_id,
            tool_name,
            args,
            scope,
            scope_key=scope_key,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
        )
        try:
            artifact_exchange.diff_register(
                server_id, root, before, scope_key, session_id=session_id, user_id=user_id
            )
        except Exception as exc:  # noqa: BLE001 — diff is auxiliary, never affect the result
            logger.warning("mcp_diff_register_failed server_id=%s error=%s", server_id, exc)
        return text


async def _call_via_session_inner(
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    scope: int | None = None,
    *,
    scope_key: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Invoke a tool through the held SDK ClientSession (any transport).

    On a connection-level failure, lazily re-open the session once and retry. If the
    server is already known-unavailable, or the auth is sticky-unavailable, or reopen
    fails, return a degraded result rather than raising — never crash the agent loop.
    """
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")

    # oauth2 server marked auth-unavailable: return directly, no call.
    if server.auth_type == "oauth2" and server._auth_unavailable:
        return _auth_unavailable_result(server_id)
    # per-user oauth: ensure the (user, agent, server) token is present and fresh. An
    # expired-but-refreshable token is refreshed in place (transparent, D7/7.3); a missing
    # token (or a genuinely un-refreshable one) triggers this user's own authorization
    # (build + DM a link) and returns a "needs authorization" result on the degrade chain —
    # never crash, never open or reuse another user's session (D8).
    if _is_per_user_oauth(server) and not await _ensure_fresh_user_token(server, user_id, agent_id):
        return await _trigger_per_user_authorization(server, user_id, agent_id)
    # per-user api-key: no refresh — a missing (user, agent, server) key returns "needs
    # credential" and triggers submission (form link / in-DM tool) per credential_input.
    if _is_per_user_apikey(server) and not _has_user_credential(server, user_id, agent_id):
        return await _trigger_per_user_credential(server, user_id, agent_id)
    # Known-unavailable server: short-circuit without touching the connection.
    if server._health is not HealthState.healthy:
        return _unavailable_result(server_id)

    # A stdio server is a host process whose mount namespace has no /workspace; translate
    # container workspace paths in the args to the run's host bind-mount source so the
    # server can read files the agent produced (scope_key disambiguates the session).
    if scope_key and server.transport == "stdio":
        from fleetent.integrations.sandbox.manager import host_workspace_dir

        args = _translate_workspace_args(args, host_workspace_dir(scope_key))

    key = _session_key(server, scope, user_id)
    # Per-user stdio: a subprocess outlives its token only until the token expires; pre-empt
    # the call by re-spawning with the store's current (refreshed) token so the subprocess
    # never authenticates with a stale token (D4).
    if (
        _stdio_token_expired(server, key)
        and await _restart_stdio_for_fresh_token(server, scope, user_id, agent_id) is None
    ):
        set_health(server, HealthState.unavailable)
        return _unavailable_result(server_id)
    session = _active_sessions.get(key)
    if session is None:
        session = await _reopen_session(server, scope, user_id, agent_id)
        if session is None:
            # An oauth genuine-auth failure during open sets the sticky flag; report it
            # specifically rather than as a connection problem.
            if server.auth_type == "oauth2" and server._auth_unavailable:
                return _auth_unavailable_result(server_id)
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)

    try:
        result = await session.call_tool(tool_name, args)
    except Exception as exc:  # noqa: BLE001 — connection drop → lazy reconnect once
        # oauth2 errors degrade (genuine→sticky auth-unavailable, transient→retryable),
        # never crash the agent loop; the sticky-flag check is robust to wrapped exceptions.
        oauth_degraded = _oauth_degraded_result(server, exc)
        if oauth_degraded is not None:
            return oauth_degraded
        # Per-user stdio 401: the subprocess's token was rejected — re-spawn with the
        # store's current (refreshed) token and retry once (D4) before any degrade.
        if _is_per_user_stdio(server) and _is_401_error(exc):
            restarted = await _restart_stdio_for_fresh_token(server, scope, user_id, agent_id)
            if restarted is None:
                set_health(server, HealthState.unavailable)
                return _unavailable_result(server_id)
            try:
                result = await restarted.call_tool(tool_name, args)
            except Exception as retry_exc:  # noqa: BLE001 — restart+retry failed → degrade
                logger.warning(
                    "mcp_stdio_401_retry_failed server_id=%s error=%s", server_id, retry_exc
                )
                set_health(server, HealthState.unavailable)
                return _unavailable_result(server_id)
            reset_health(server)
            _touch_host(key)
            text = _result_to_text(result)
            return _rewrite_result_paths(server_id, text, scope_key, session_id, user_id)
        if not _is_disconnect_error(exc):
            raise
        new_session = await _reopen_session(server, scope, user_id)
        if new_session is None:
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)
        try:
            result = await new_session.call_tool(tool_name, args)
        except Exception as retry_exc:  # noqa: BLE001 — reopen+retry still failed → degrade
            oauth_degraded = _oauth_degraded_result(server, retry_exc)
            if oauth_degraded is not None:
                return oauth_degraded
            logger.warning("mcp_call_retry_failed server_id=%s error=%s", server_id, retry_exc)
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)
        reset_health(server)  # retry succeeded → server is healthy again
    _touch_host(key)
    text = _result_to_text(result)
    return _rewrite_result_paths(server_id, text, scope_key, session_id, user_id)


# Public API. `scope` keys the (scope, server_id) registry: None = global (startup)
# servers; an int = an agent-scoped registration. A scope with no matching server_id
# raises rather than silently falling back to the global server (agent isolation).
async def call_tool(
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    scope: int | None = None,
    *,
    scope_key: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    return await _call_via_session(
        server_id,
        tool_name,
        args,
        scope,
        scope_key=scope_key,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
    )


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


async def _invoke_utility(session: Any, util_name: str, args: dict[str, Any]) -> Any:
    """Dispatch one resources/prompts utility method on a held SDK ClientSession."""
    if util_name == "list_resources":
        return await session.list_resources()
    if util_name == "read_resource":
        return await session.read_resource(args.get("uri"))
    if util_name == "list_prompts":
        return await session.list_prompts()
    if util_name == "get_prompt":
        return await session.get_prompt(args.get("name"), args.get("arguments"))
    raise ValueError(f"Unknown MCP utility: {util_name}")


async def _call_utility(
    server_id: str,
    util_name: str,
    args: dict[str, Any],
    scope: int | None = None,
    *,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Dispatch a resources/prompts utility tool through the held SDK ClientSession.

    Same auth/health/lazy-reconnect contract as ``_call_via_session`` — all transports go
    through one session method; a dropped connection re-opens once and retries. ``user_id``
    routes to the caller's per-user session for a per-user oauth server (None slot otherwise);
    ``agent_id`` completes the per-user token isolation triple.
    """
    server = _server_registry.get((scope, server_id))
    if server is None:
        raise KeyError(f"Unknown MCP server: {server_id}")
    if server.auth_type == "oauth2" and server._auth_unavailable:
        return _auth_unavailable_result(server_id)
    # per-user oauth: refresh-if-expired then trigger authorization on a missing/dead token.
    if _is_per_user_oauth(server) and not await _ensure_fresh_user_token(server, user_id, agent_id):
        return await _trigger_per_user_authorization(server, user_id, agent_id)
    # per-user api-key: a missing key triggers credential submission (no refresh).
    if _is_per_user_apikey(server) and not _has_user_credential(server, user_id, agent_id):
        return await _trigger_per_user_credential(server, user_id, agent_id)
    if server._health is not HealthState.healthy:
        return _unavailable_result(server_id)

    key = _session_key(server, scope, user_id)
    session = _active_sessions.get(key)
    if session is None:
        session = await _reopen_session(server, scope, user_id, agent_id)
        if session is None:
            if server.auth_type == "oauth2" and server._auth_unavailable:
                return _auth_unavailable_result(server_id)
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)

    try:
        result = await _invoke_utility(session, util_name, args)
    except Exception as exc:  # noqa: BLE001 — connection drop → lazy reconnect once
        oauth_degraded = _oauth_degraded_result(server, exc)
        if oauth_degraded is not None:
            return oauth_degraded
        if not _is_disconnect_error(exc):
            raise
        new_session = await _reopen_session(server, scope, user_id, agent_id)
        if new_session is None:
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)
        try:
            result = await _invoke_utility(new_session, util_name, args)
        except Exception as retry_exc:  # noqa: BLE001 — reopen+retry still failed → degrade
            oauth_degraded = _oauth_degraded_result(server, retry_exc)
            if oauth_degraded is not None:
                return oauth_degraded
            logger.warning("mcp_utility_retry_failed server_id=%s error=%s", server_id, retry_exc)
            set_health(server, HealthState.unavailable)
            return _unavailable_result(server_id)
        reset_health(server)
    return _jsonify(result)


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

    async def call(tool_context: Any = None, **kwargs: object) -> str:
        # tool_context binds to this param (never into kwargs → never leaks to MCP args).
        # principal.user_id routes a per-user oauth server's utility call to that user's session;
        # agent_name completes the per-user token isolation triple (Group 6, D1).
        principal = getattr(tool_context, "principal", None)
        user_id = getattr(principal, "user_id", None)
        agent_id = getattr(tool_context, "agent_name", None)
        return await _call_utility(
            server.id,
            util_name,
            dict(kwargs),
            server._agent_scope,
            user_id=user_id,
            agent_id=agent_id,
        )

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
