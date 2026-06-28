"""Unit tests for the SDK-provider-backed oauth2 client_credentials path:
`_FleetentClientCredentialsProvider` (preseed + sticky/transient), `_oauth_auth` wiring,
the call-path error mapping, and an end-to-end auth_flow drive over httpx MockTransport.
Mocks the SDK provider's I/O, never a real server."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from mcp.client.auth import OAuthTokenError

import fleetent.integrations.mcp.client as mc
from fleetent.config import McpServerSettings
from fleetent.integrations.mcp.client import McpServerConfig, OAuthAuthUnavailableError


def _oauth_server(sid: str = "o") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://mcp.example/mcp",
        auth_type="oauth2",
        token_url="https://auth.example/oauth/token",
        client_id="cid",
        client_secret_env="OAUTH_SECRET_X",
        scope="read write",
    )


def _resp(status: int, *, json: dict | None = None, text: str = "") -> httpx.Response:
    req = httpx.Request("POST", "https://auth.example/oauth/token")
    if json is not None:
        return httpx.Response(status, json=json, request=req)
    return httpx.Response(status, text=text, request=req)


# ── provider construction + preseed (D2/D3) ───────────────────────────────────


async def test_provider_preseeds_token_endpoint_from_token_url(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    prov = mc._FleetentClientCredentialsProvider(_oauth_server())
    await prov._initialize()
    assert str(prov.context.oauth_metadata.token_endpoint).rstrip("/") == (
        "https://auth.example/oauth/token"
    )
    assert prov._get_token_endpoint().rstrip("/") == "https://auth.example/oauth/token"


async def test_provider_maps_config(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    prov = mc._FleetentClientCredentialsProvider(_oauth_server())
    await prov._initialize()
    info = prov.context.client_info
    assert info.client_id == "cid"
    assert info.client_secret == "shh"
    assert info.token_endpoint_auth_method == "client_secret_post"
    assert prov.context.client_metadata.scope == "read write"


# ── sticky vs transient on the token response (D4) ─────────────────────────────


async def test_handle_token_response_genuine_is_sticky(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    server = _oauth_server()
    prov = mc._FleetentClientCredentialsProvider(server)
    await prov._initialize()
    with pytest.raises(OAuthAuthUnavailableError):
        await prov._handle_token_response(_resp(400, json={"error": "invalid_client"}))
    assert server._auth_unavailable is True


async def test_handle_token_response_transient_not_sticky(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    server = _oauth_server()
    prov = mc._FleetentClientCredentialsProvider(server)
    await prov._initialize()
    with pytest.raises(OAuthTokenError):
        await prov._handle_token_response(_resp(500, text="upstream boom"))
    assert server._auth_unavailable is False


# ── _oauth_auth wiring + transport auth= (Task 2) ─────────────────────────────


def test_oauth_auth_returns_sdk_provider(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    auth = mc._oauth_auth(_oauth_server())
    assert isinstance(auth, mc._FleetentClientCredentialsProvider)


def test_oauth_auth_none_for_api_key():
    server = McpServerConfig(id="k", transport="http", url="https://h/mcp", auth_type="api_key")
    assert mc._oauth_auth(server) is None


def test_transport_cm_passes_sdk_provider_as_auth(monkeypatch):
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    captured: dict[str, Any] = {}

    def fake(*a: Any, auth: Any = None, **k: Any) -> str:
        captured["auth"] = auth
        return "cm"

    monkeypatch.setattr(mc, "streamablehttp_client", fake)
    mc._transport_cm(_oauth_server(), headers={})
    assert isinstance(captured["auth"], mc._FleetentClientCredentialsProvider)


# ── call-path error mapping (Task 3 / D5) ─────────────────────────────────────


class _GenuineAuthFailSession:
    """call surfaces a genuine credential failure: sets sticky (like the provider's
    _handle_token_response side effect) then raises OAuthAuthUnavailableError."""

    def __init__(self, server: McpServerConfig) -> None:
        self._server = server
        self.calls = 0

    async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
        self.calls += 1
        self._server._auth_unavailable = True
        raise OAuthAuthUnavailableError("bad credentials")


class _TransientTokenFailSession:
    """call surfaces a transient token-endpoint error (5xx) — OAuthTokenError, no sticky."""

    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
        self.calls += 1
        raise OAuthTokenError("Token exchange failed (503): upstream down")


async def test_call_genuine_auth_failure_sticky_degrades(monkeypatch):
    server = _oauth_server("g")
    sess = _GenuineAuthFailSession(server)
    monkeypatch.setitem(mc._server_registry, (None, "g"), server)
    monkeypatch.setitem(mc._active_sessions, (None, "g"), sess)

    out = await mc.call_tool("g", "t", {})
    assert "authentication unavailable" in out.lower() or "不可用" in out
    assert server._auth_unavailable is True
    # sticky → second call short-circuits without touching the session
    out2 = await mc.call_tool("g", "t", {})
    assert "authentication unavailable" in out2.lower() or "不可用" in out2
    assert sess.calls == 1


async def test_call_transient_token_error_degrades_not_sticky(monkeypatch):
    server = _oauth_server("tr")
    sess = _TransientTokenFailSession()
    monkeypatch.setitem(mc._server_registry, (None, "tr"), server)
    monkeypatch.setitem(mc._active_sessions, (None, "tr"), sess)

    out = await mc.call_tool("tr", "t", {})  # must NOT raise (no crash on transient)
    assert "unavailable" in out.lower() or "不可用" in out
    assert server._auth_unavailable is False  # transient → retryable, not sticky


# ── end-to-end auth_flow over real SDK provider + httpx MockTransport (Task 4) ─


async def test_auth_flow_end_to_end_401_discover_token_retry(monkeypatch):
    """Drive the real SDK provider's async_auth_flow through the full reactive sequence:
    tokenless request → 401 → .well-known probes (404, fall back to preseed) → token POST
    to the explicit token_url → retry with Bearer. Validates D1/D2/D3 against real httpx."""
    monkeypatch.setenv("OAUTH_SECRET_X", "shh")
    server = _oauth_server()
    state = {"token_issued": False, "token_post_url": None, "token_post_body": None}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if ".well-known" in url:
            return httpx.Response(404)  # no discovery → fall back to preseeded token_url
        if request.method == "POST" and url.rstrip("/") == server.token_url.rstrip("/"):
            state["token_issued"] = True
            state["token_post_url"] = url
            state["token_post_body"] = request.content.decode()
            return httpx.Response(
                200, json={"access_token": "AT-123", "token_type": "Bearer", "expires_in": 3600}
            )
        # the MCP request itself
        if not state["token_issued"]:
            return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})
        assert request.headers.get("Authorization") == "Bearer AT-123"
        return httpx.Response(200, json={"ok": True})

    provider = mc._FleetentClientCredentialsProvider(server)
    async with httpx.AsyncClient(auth=provider, transport=httpx.MockTransport(handler)) as client:
        resp = await client.get(server.url, headers={"MCP-Protocol-Version": "2025-11-25"})

    assert resp.status_code == 200
    assert state["token_issued"] is True
    # token POST went to the explicit (preseeded) token_url, with client_credentials + post auth
    assert state["token_post_url"].rstrip("/") == server.token_url.rstrip("/")
    assert "grant_type=client_credentials" in state["token_post_body"]
    assert "client_secret=shh" in state["token_post_body"]  # client_secret_post


# ── _http_headers: oauth bearer rides auth=, not the static headers ───────────


async def test_http_headers_omits_oauth_bearer():
    # The oauth2 bearer is injected by the SDK provider via the transport auth=, never baked
    # into the session's static headers.
    headers = await mc._http_headers(_oauth_server())
    assert "Authorization" not in headers


async def test_http_headers_keeps_api_key_bearer(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")
    server = McpServerConfig(
        id="k", transport="http", url="https://h/mcp", auth_type="api_key", api_key_env="MY_KEY"
    )
    headers = await mc._http_headers(server)
    assert headers["Authorization"] == "Bearer secret"


async def test_http_headers_keeps_api_key_bearer_for_materialized_settings(monkeypatch):
    monkeypatch.setenv("MATERIALIZED_KEY", "secret")
    server = McpServerConfig.from_settings(
        McpServerSettings(
            id="k",
            transport="http",
            url="https://h/mcp",
            auth_type="api_key",
            api_key_env="MATERIALIZED_KEY",
        )
    )
    headers = await mc._http_headers(server)
    assert headers["Authorization"] == "Bearer secret"
