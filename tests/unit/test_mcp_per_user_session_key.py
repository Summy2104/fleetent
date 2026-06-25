"""Unit tests for Group 3: per-user oauth session-key extension + routing.

Covers the backward-compatible session-key dimension: per-user oauth servers
(``oauth_grant == "authorization_code"``) extend the live-session key from
``(scope, server_id)`` to ``(scope, server_id, user_id)``; every other server keeps
``(scope, server_id)`` byte-identically. The SDK transport / ClientSession are stubbed —
no real wire, DB, or FastAPI.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig


def _tool(name: str, desc: str = "d") -> SimpleNamespace:
    return SimpleNamespace(
        name=name, description=desc, inputSchema={"type": "object", "properties": {}}
    )


class _FakeSession:
    """Minimal stand-in for mcp.ClientSession that records its calls."""

    def __init__(self, tools: list[Any] | None = None) -> None:
        self._tools = tools or []
        self.calls: list[tuple[str, dict]] = []

    async def initialize(self) -> Any:
        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def list_tools(self, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=self._tools, nextCursor=None)

    async def call_tool(self, name: str, args: dict) -> Any:
        self.calls.append((name, args))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            structuredContent=None,
            isError=False,
        )


@contextlib.asynccontextmanager
async def _fake_transport(*args: Any, **kwargs: Any):
    yield ("read", "write", None)


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    monkeypatch.setattr(mc, "_session_hosts", {})
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    yield


def _per_user_server(sid: str = "puo") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
    )


def _plain_oauth_server(sid: str = "cc") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="client_credentials",
    )


def _plain_http_server(sid: str = "plain") -> McpServerConfig:
    return McpServerConfig(id=sid, transport="http", url="https://host/mcp")


# ── _is_per_user_oauth predicate ───────────────────────────────────────────────


def test_is_per_user_oauth_true_only_for_authcode():
    assert mc._is_per_user_oauth(_per_user_server()) is True
    assert mc._is_per_user_oauth(_plain_oauth_server()) is False
    assert mc._is_per_user_oauth(_plain_http_server()) is False


# ── _session_key helper ─────────────────────────────────────────────────────────


def test_session_key_plain_server_excludes_user():
    server = _plain_http_server("plain")
    # Plain servers keep the legacy 2-tuple key regardless of any user_id (backward compat).
    assert mc._session_key(server, None, "u1") == (None, "plain")
    assert mc._session_key(server, 7, None) == (7, "plain")


def test_session_key_per_user_server_includes_user():
    server = _per_user_server("puo")
    assert mc._session_key(server, None, "u1") == (None, "puo", "u1")
    assert mc._session_key(server, None, "u2") == (None, "puo", "u2")
    # A None user dimension stays None even for a per-user server (unroutable → key sentinel).
    assert mc._session_key(server, None, None) == (None, "puo", None)


# ── _call_window_lock granularity ──────────────────────────────────────────────


def test_call_window_lock_per_user_distinct_per_user():
    server = _per_user_server("puo")
    lock_a = mc._call_window_lock_for(server, "uA")
    lock_b = mc._call_window_lock_for(server, "uB")
    lock_a2 = mc._call_window_lock_for(server, "uA")
    assert lock_a is not lock_b  # different users do not serialize against each other
    assert lock_a is lock_a2  # same user reuses its lock


def test_call_window_lock_plain_server_is_per_server():
    server = _plain_http_server("plain")
    lock_a = mc._call_window_lock_for(server, "uA")
    lock_b = mc._call_window_lock_for(server, "uB")
    # Non-per-user server keeps the single per-server lock regardless of user.
    assert lock_a is lock_b is server._call_window_lock


# ── routing: per-user server keys sessions by user ─────────────────────────────


async def test_per_user_server_routes_to_distinct_sessions(monkeypatch):
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    # Group 6: a routable user with a token reaches the session-open path (no-token would
    # short-circuit to an authorization trigger instead).
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: object())

    opened: list[str | None] = []

    async def _fake_open(srv, scope, user_id=None, agent_id=None):
        opened.append(user_id)
        sess = _FakeSession()
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    await mc.call_tool("puo", "do", {}, user_id="uA")
    await mc.call_tool("puo", "do", {}, user_id="uB")

    assert (None, "puo", "uA") in mc._active_sessions
    assert (None, "puo", "uB") in mc._active_sessions
    assert opened == ["uA", "uB"]


async def test_per_user_same_user_reuses_session(monkeypatch):
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: object())

    open_count = {"n": 0}

    async def _fake_open(srv, scope, user_id=None, agent_id=None):
        open_count["n"] += 1
        sess = _FakeSession()
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    await mc.call_tool("puo", "do", {}, user_id="uA")
    await mc.call_tool("puo", "do", {}, user_id="uA")

    assert open_count["n"] == 1  # second call reused the existing session


async def test_plain_server_ignores_user_dim(monkeypatch):
    """Backward compat: a non-per-user server keys sessions by (scope, server_id) only."""
    server = _plain_http_server("plain")
    mc._server_registry[(None, "plain")] = server

    async def _fake_open(srv, scope, user_id=None, agent_id=None):
        sess = _FakeSession()
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    await mc.call_tool("plain", "do", {}, user_id="uA")
    # Even with a user_id present, the key stays the legacy 2-tuple (no user dimension).
    assert (None, "plain") in mc._active_sessions


async def test_per_user_server_missing_user_returns_auth_unavailable(monkeypatch):
    """A per-user oauth call with no user_id is unroutable → degraded, not a crash."""
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    async def _fake_open(srv, scope, user_id=None, agent_id=None):  # must not be reached
        raise AssertionError("should not open a session without a user_id")

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    out = await mc.call_tool("puo", "do", {}, user_id=None)
    assert "puo" in out
    assert "auth" in out.lower() or "authoriz" in out.lower() or "授权" in out


# ── tool name stays user-agnostic ──────────────────────────────────────────────


async def test_per_user_tool_name_user_agnostic(monkeypatch):
    """Group 3.2: per-user oauth tools register as {server_id}__{tool} (no user dim)."""
    session = _FakeSession(tools=[_tool("search")])

    monkeypatch.setattr(mc, "streamablehttp_client", lambda *a, **k: _fake_transport())

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield session

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))
    import fleetent.tools.registry as tr

    await mc._register_session_server(_per_user_server("puo"), scope=None)
    assert "puo__search" in tr._registry
    # No user dimension leaked into any registered tool name.
    assert all("__" in n and "uA" not in n for n in tr._registry)
