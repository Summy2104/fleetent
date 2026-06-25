"""Unit tests for Group 4: per-user http session + per-request Bearer injection.

Covers the custom ``_PerUserBearerAuth`` (per-request token read → refresh-transparent),
the per-user http session construction (each user a dedicated ClientSession bound to that
user's auth), and the ``streamablehttp_client`` re-export shim (legacy entry still usable,
non-per-user http behavior unchanged). No real wire, DB, or FastAPI: the SDK transport /
ClientSession and ``resolve_user_token`` are stubbed.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import UserToken


def _per_user_server(sid: str = "puo") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
    )


def _plain_http_server(sid: str = "plain") -> McpServerConfig:
    return McpServerConfig(id=sid, transport="http", url="https://host/mcp")


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://host/mcp")


# ── _PerUserBearerAuth: per-request token read ─────────────────────────────────


def test_per_user_auth_injects_current_token():
    auth = mc._PerUserBearerAuth(lambda: "tok-1")
    flow = auth.auth_flow(_request())
    sent = next(flow)
    assert sent.headers["Authorization"] == "Bearer tok-1"


def test_per_user_auth_no_token_sets_no_header():
    """No token → no Authorization header (resource end decides 401 / degrade)."""
    auth = mc._PerUserBearerAuth(lambda: None)
    flow = auth.auth_flow(_request())
    sent = next(flow)
    assert "Authorization" not in sent.headers


def test_per_user_auth_reads_token_each_request_refresh_transparent():
    """Token changing between requests → the next request carries the new token."""
    tokens = iter(["tok-old", "tok-new"])
    auth = mc._PerUserBearerAuth(lambda: next(tokens))

    first = next(auth.auth_flow(_request()))
    second = next(auth.auth_flow(_request()))

    assert first.headers["Authorization"] == "Bearer tok-old"
    assert second.headers["Authorization"] == "Bearer tok-new"


def test_per_user_auth_drive_over_mock_transport():
    """auth_flow integrates with a real httpx.Client over a MockTransport (no network)."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    auth = mc._PerUserBearerAuth(lambda: "drive-tok")
    with httpx.Client(transport=transport, auth=auth) as client:
        client.get("https://host/mcp")
    assert seen == ["Bearer drive-tok"]


# ── token getter closes over (server_id, user_id, agent_id) ─────────────────────


def test_token_getter_closes_over_triple(monkeypatch):
    captured: list[tuple[str, str, str | None]] = []

    def fake_resolve(server_id, user_id, agent_id=None):
        captured.append((server_id, user_id, agent_id))
        return UserToken(access_token="abc", refresh_token=None, expires_at=None, scope=None)

    monkeypatch.setattr(mc, "resolve_user_token", fake_resolve)
    getter = mc._per_user_token_getter("srv", "uX", "agent7")
    assert getter() == "abc"
    assert captured == [("srv", "uX", "agent7")]


def test_token_getter_returns_none_when_no_token(monkeypatch):
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    getter = mc._per_user_token_getter("srv", "uX", None)
    assert getter() is None


# ── per-user http session construction ─────────────────────────────────────────


class _FakeSession:
    def __init__(self, tools: list[Any] | None = None) -> None:
        self._tools = tools or []

    async def initialize(self) -> Any:
        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def list_tools(self, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=self._tools, nextCursor=None)


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


async def test_per_user_http_session_built_with_user_bound_auth(monkeypatch):
    """A per-user oauth http session opens a transport bound to that user's bearer auth."""
    captured: list[dict[str, Any]] = []

    def fake_new_transport(url, *, http_client=None, **kwargs):
        captured.append({"url": url, "http_client": http_client})
        return _fake_transport()

    monkeypatch.setattr(mc, "streamable_http_client", fake_new_transport)

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield _FakeSession()

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))
    monkeypatch.setattr(
        mc,
        "resolve_user_token",
        lambda *a, **k: UserToken(
            access_token="UTOK", refresh_token=None, expires_at=None, scope=None
        ),
    )

    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")

    assert (None, "puo", "uA") in mc._active_sessions
    assert len(captured) == 1
    client = captured[0]["http_client"]
    assert isinstance(client, httpx.AsyncClient)
    # The client's auth is the per-user bearer auth bound to this user's token.
    assert isinstance(client.auth, mc._PerUserBearerAuth)
    sent = next(client.auth.auth_flow(_request()))
    assert sent.headers["Authorization"] == "Bearer UTOK"


async def test_different_users_get_distinct_sessions(monkeypatch):
    monkeypatch.setattr(mc, "streamable_http_client", lambda *a, **k: _fake_transport())

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield _FakeSession()

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)

    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    s_a = await mc._open_session_for(server, None, user_id="uA")
    s_b = await mc._open_session_for(server, None, user_id="uB")

    assert s_a is not s_b
    assert (None, "puo", "uA") in mc._active_sessions
    assert (None, "puo", "uB") in mc._active_sessions


# ── shim compatibility: non-per-user http unchanged ────────────────────────────


def test_streamablehttp_client_shim_exists_and_callable():
    """The legacy entry point is preserved (re-export shim) and is callable."""
    assert callable(mc.streamablehttp_client)


async def test_plain_http_session_uses_new_api_under_shim(monkeypatch):
    """Non-per-user http migrates to the new API via the shim (behavior unchanged)."""
    new_api_calls: list[str] = []

    def fake_new_transport(url, *, http_client=None, **kwargs):
        new_api_calls.append(url)
        return _fake_transport()

    monkeypatch.setattr(mc, "streamable_http_client", fake_new_transport)

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield _FakeSession()

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))

    server = _plain_http_server("plain")
    mc._server_registry[(None, "plain")] = server

    await mc._open_session_for(server, None, user_id=None)

    # Plain server keyed without user dimension; opened via the (shim-backed) new API.
    assert (None, "plain") in mc._active_sessions
    assert new_api_calls == ["https://host/mcp"]


async def test_shim_builds_http_client_with_headers_and_timeout(monkeypatch):
    """The shim translates legacy headers/timeout into an AsyncClient on the new API."""
    captured: dict[str, Any] = {}

    def fake_new_transport(url, *, http_client=None, **kwargs):
        captured["url"] = url
        captured["http_client"] = http_client
        return _fake_transport()

    monkeypatch.setattr(mc, "streamable_http_client", fake_new_transport)

    cm = mc.streamablehttp_client(
        "https://host/mcp",
        headers={"X-Api-Key": "k"},
        timeout=5.0,
        sse_read_timeout=90.0,
    )
    async with cm:
        pass

    assert captured["url"] == "https://host/mcp"
    client = captured["http_client"]
    assert isinstance(client, httpx.AsyncClient)
    assert client.headers["X-Api-Key"] == "k"


async def test_plain_oauth_http_uses_client_credentials_auth(monkeypatch):
    """A client_credentials oauth server keeps the SDK provider as the client's auth."""
    captured: dict[str, Any] = {}

    def fake_new_transport(url, *, http_client=None, **kwargs):
        captured["http_client"] = http_client
        return _fake_transport()

    monkeypatch.setattr(mc, "streamable_http_client", fake_new_transport)

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield _FakeSession()

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))
    monkeypatch.setenv("CC_SECRET", "shh")

    server = McpServerConfig(
        id="cc",
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="client_credentials",
        token_url="https://auth/token",
        client_id="cid",
        client_secret_env="CC_SECRET",
    )
    mc._server_registry[(None, "cc")] = server

    await mc._open_session_for(server, None, user_id=None)

    client = captured["http_client"]
    assert isinstance(client, httpx.AsyncClient)
    # client_credentials → the SDK provider rides as the client's auth (not per-user bearer).
    assert isinstance(client.auth, mc._FleetentClientCredentialsProvider)
    assert not isinstance(client.auth, mc._PerUserBearerAuth)
