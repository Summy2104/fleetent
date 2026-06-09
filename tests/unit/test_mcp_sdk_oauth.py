"""Unit tests for the SDK-based OAuth2 client_credentials auth: a custom httpx.Auth
injected via the SDK transport `auth=`, with per-request token attachment and a single
401 refresh+retry. Mocks the token-resolution seam (not the wire)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig, OAuthAuthUnavailableError


def _oauth_server(sid: str = "o") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        token_url="https://auth/token",
        client_id="cid",
    )


# ── _ClientCredentialsAuth.async_auth_flow ────────────────────────────────────


async def test_auth_flow_attaches_bearer(monkeypatch):
    async def fake_resolve(server: McpServerConfig) -> str:
        return "tok1"

    monkeypatch.setattr(mc, "_resolve_oauth_token", fake_resolve)
    auth = mc._ClientCredentialsAuth(_oauth_server())
    gen = auth.async_auth_flow(httpx.Request("POST", "https://host/mcp"))

    sent = await gen.__anext__()
    assert sent.headers["Authorization"] == "Bearer tok1"
    # a non-401 response ends the flow (no retry)
    with pytest.raises(StopAsyncIteration):
        await gen.asend(httpx.Response(200, request=sent))


async def test_auth_flow_refreshes_and_retries_once_on_401(monkeypatch):
    tokens = iter(["stale", "fresh"])
    cleared: list[str] = []

    async def fake_resolve(server: McpServerConfig) -> str:
        return next(tokens)

    monkeypatch.setattr(mc, "_resolve_oauth_token", fake_resolve)
    server = _oauth_server()
    monkeypatch.setattr(server._token_store, "clear", lambda sid: cleared.append(sid))
    auth = mc._ClientCredentialsAuth(server)
    gen = auth.async_auth_flow(httpx.Request("POST", "https://host/mcp"))

    sent1 = await gen.__anext__()
    assert sent1.headers["Authorization"] == "Bearer stale"
    # 401 → clear cache, refresh, retry once with the fresh token
    sent2 = await gen.asend(httpx.Response(401, request=sent1))
    assert cleared == ["o"]
    assert sent2.headers["Authorization"] == "Bearer fresh"
    # a success on the retry ends the flow (only one retry)
    with pytest.raises(StopAsyncIteration):
        await gen.asend(httpx.Response(200, request=sent2))


async def test_auth_flow_no_retry_on_non_401(monkeypatch):
    calls = {"n": 0}

    async def fake_resolve(server: McpServerConfig) -> str:
        calls["n"] += 1
        return "tok"

    monkeypatch.setattr(mc, "_resolve_oauth_token", fake_resolve)
    auth = mc._ClientCredentialsAuth(_oauth_server())
    gen = auth.async_auth_flow(httpx.Request("POST", "https://host/mcp"))

    sent = await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.asend(httpx.Response(500, request=sent))  # 5xx is not a token-expiry signal
    assert calls["n"] == 1  # resolved once, no refresh


async def test_auth_flow_genuine_failure_propagates(monkeypatch):
    async def fake_resolve(server: McpServerConfig) -> str:
        raise OAuthAuthUnavailableError("bad credentials")

    monkeypatch.setattr(mc, "_resolve_oauth_token", fake_resolve)
    auth = mc._ClientCredentialsAuth(_oauth_server())
    gen = auth.async_auth_flow(httpx.Request("POST", "https://host/mcp"))

    with pytest.raises(OAuthAuthUnavailableError):
        await gen.__anext__()


# ── transport auth= wiring + _http_headers ────────────────────────────────────


def _capture_transport_auth(monkeypatch) -> dict:
    captured: dict[str, Any] = {}

    def fake(*a: Any, auth: Any = None, **k: Any) -> str:
        captured["auth"] = auth
        return "cm"

    monkeypatch.setattr(mc, "streamablehttp_client", fake)
    monkeypatch.setattr(mc, "sse_client", fake)
    return captured


def test_transport_cm_passes_oauth_auth_for_oauth2(monkeypatch):
    captured = _capture_transport_auth(monkeypatch)
    mc._transport_cm(_oauth_server(), headers={})
    assert isinstance(captured["auth"], mc._ClientCredentialsAuth)


def test_transport_cm_no_auth_for_api_key(monkeypatch):
    captured = _capture_transport_auth(monkeypatch)
    server = McpServerConfig(id="k", transport="http", url="https://h/mcp", auth_type="api_key")
    mc._transport_cm(server, headers={})
    assert captured["auth"] is None


async def test_http_headers_omits_oauth_bearer(monkeypatch):
    # The oauth bearer now rides the transport auth=, not the static session headers.
    async def fake_resolve(server: McpServerConfig) -> str:
        return "tok"

    monkeypatch.setattr(mc, "_resolve_oauth_token", fake_resolve)
    headers = await mc._http_headers(_oauth_server())
    assert "Authorization" not in headers


async def test_http_headers_keeps_api_key_bearer(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")
    server = McpServerConfig(
        id="k", transport="http", url="https://h/mcp", auth_type="api_key", api_key_env="MY_KEY"
    )
    headers = await mc._http_headers(server)
    assert headers["Authorization"] == "Bearer secret"


# ── auth-unavailable bubbling from the auth flow → degraded result ────────────


class _AuthFailSession:
    """A held session whose call surfaces a genuine oauth failure (sticky set, like the
    real auth flow setting _auth_unavailable inside _resolve_oauth_token before raising)."""

    def __init__(self, server: McpServerConfig) -> None:
        self._server = server
        self.calls = 0

    async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
        self.calls += 1
        self._server._auth_unavailable = True
        raise OAuthAuthUnavailableError("token endpoint rejected credentials")


async def test_call_via_session_oauth_unavailable_returns_degraded(monkeypatch):
    server = _oauth_server("o")
    sess = _AuthFailSession(server)
    monkeypatch.setitem(mc._server_registry, (None, "o"), server)
    monkeypatch.setitem(mc._active_sessions, (None, "o"), sess)

    # First call: the auth flow's genuine failure bubbles → degraded text, not an exception.
    out = await mc.call_tool("o", "t", {})
    assert "authentication unavailable" in out.lower() or "不可用" in out
    assert sess.calls == 1

    # Second call: sticky flag short-circuits upfront — the session is not touched again.
    out2 = await mc.call_tool("o", "t", {})
    assert "authentication unavailable" in out2.lower() or "不可用" in out2
    assert sess.calls == 1
