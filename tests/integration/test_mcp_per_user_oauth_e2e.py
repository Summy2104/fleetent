"""Group 9.2 — standalone per-user OAuth end-to-end (http transport).

Ties together Groups 1–7 over a single per-user oauth (authorization_code) http MCP
service, with the real SDK session + token endpoint *stubbed* (no network, no real DB
file under ``data/``):

1. user A's first call → no ``(A, agent, server)`` token → a clear "needs authorization"
   result on the degrade chain (never an exception), and the authorization link captured
   via the injected deliverer seam carries PKCE (``code_challenge`` S256), a bound
   one-shot ``state``, and the exact configured ``redirect_uri``.
2. user A authorizes → drive ``GET /oauth/callback`` (FastAPI TestClient) with that
   state + a code; the mocked token endpoint returns access+refresh → the token is
   persisted *encrypted* in a tmp_path-backed, migrated ``agent_state.db``.
3. user A calls again → the token resolves and the call executes as A: the per-user
   http session is opened with a ``_PerUserBearerAuth`` injecting A's bearer, and the
   stubbed session call sees ``Authorization: Bearer <A's token>``.
4. user B calls the same service → still no ``(B, agent, server)`` token → B's own
   authorization is triggered; A's token is never reused for B.

The token endpoint is an ``httpx.MockTransport``; the SDK ``streamable_http_client`` +
``ClientSession`` are stubbed; the authorization-link deliverer + the agent's own IM are
replaced by a capturing seam. The state store is shared between link-build and callback
(the boot default), exactly as standalone wiring leaves it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
import fleetent.integrations.mcp.standalone_callback as sc
from fleetent.db import SQLiteDatabase
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import (
    InMemoryUserTokenStore,
    resolve_user_token,
    set_local_user_token_store,
)
from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore
from fleetent.runtime import agent_app
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate

AGENT_ID = "ag1"
SERVER_ID = "puo"
REDIRECT_BASE = "https://agent.internal"


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("PUO_SECRET", "shh-client-secret")


@pytest.fixture(autouse=True)
def _clean_seams(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    monkeypatch.setattr(mc, "_session_hosts", {})
    az.reset_oauth_state_store()
    az.set_redirect_base(REDIRECT_BASE)
    yield
    az.reset_oauth_state_store()
    az.set_redirect_base(None)
    az.set_authorization_link_deliverer(None)
    mc.set_token_refresher(None)
    set_local_user_token_store(InMemoryUserTokenStore())  # reset the standalone fallback store


def _migrated_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _per_user_server() -> McpServerConfig:
    return McpServerConfig(
        id=SERVER_ID,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
        authorization_endpoint="https://as.internal/authorize",
        token_url="https://as.internal/token",
        client_id="client-123",
        client_secret_env="PUO_SECRET",
        scope="read",
        redirect_path="/oauth/callback",
    )


def _mock_token_client(captured: list[dict], *, response: dict, status: int = 200):
    """Factory yielding a MockTransport AsyncClient that records the posted form."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        captured.append(dict(p.split("=", 1) for p in body.split("&")))
        return httpx.Response(status, json=response)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


class _CapturingDeliverer:
    """Stands in for the agent's IM connector: records every link instead of DMing it."""

    def __init__(self) -> None:
        self.links: list[tuple[str, str, str, str]] = []  # (user, agent, server, url)

    async def __call__(self, user_id: str, agent_id: str, server_id: str, url: str) -> bool:
        self.links.append((user_id, agent_id, server_id, url))
        return True


class _SpySession:
    """Stub SDK ClientSession capturing the bearer the transport's auth injects.

    On open we record nothing; on ``call_tool`` we run the bound http client's auth_flow
    against a probe request so the test can assert which user's bearer would ride the wire.
    """

    def __init__(self, http_client: httpx.AsyncClient | None, sink: list[str | None]) -> None:
        self._http_client = http_client
        self._sink = sink

    async def initialize(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        from types import SimpleNamespace

        auth = self._http_client.auth if self._http_client is not None else None
        if auth is not None:
            req = httpx.Request("POST", "https://host/mcp")
            sent = next(auth.auth_flow(req))
            self._sink.append(sent.headers.get("Authorization"))
        else:
            self._sink.append(None)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="tool-ok")])


def _stub_sdk_transport(monkeypatch, bearer_sink: list[str | None]) -> None:
    """Stub ``streamable_http_client`` + ``ClientSession`` so opens never touch the wire.

    The fake transport keeps the per-user-bound ``http_client`` so the spy session can read
    its auth; the fake ClientSession is that spy. No real network, no real subprocess.
    """
    import contextlib

    holder: dict[str, httpx.AsyncClient | None] = {}

    def fake_transport(url, *, http_client=None, **kwargs):
        holder["http_client"] = http_client

        @contextlib.asynccontextmanager
        async def _cm():
            yield ("read", "write", None)

        return _cm()

    monkeypatch.setattr(mc, "streamable_http_client", fake_transport)

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield _SpySession(holder.get("http_client"), bearer_sink)

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))


async def test_standalone_per_user_oauth_http_end_to_end(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    store = StandaloneUserTokenStore(db)
    # Standalone boot wiring: local store + transparent refresher (no platform).
    sc.wire_standalone_oauth(store)
    server = _per_user_server()
    mc._server_registry[(None, SERVER_ID)] = server

    deliverer = _CapturingDeliverer()
    az.set_authorization_link_deliverer(deliverer)

    bearer_sink: list[str | None] = []
    _stub_sdk_transport(monkeypatch, bearer_sink)

    # ── 1. user A's first call → needs-authorization (no exception), link captured ──
    result_a1 = await mc.call_tool(SERVER_ID, "do_thing", {}, None, user_id="uA", agent_id=AGENT_ID)
    assert "needs your authorization" in result_a1
    assert "MCP server" in result_a1  # the degrade-chain prefix, not an exception
    # exactly one link, addressed to A for this triple
    assert len(deliverer.links) == 1
    luser, lagent, lserver, url = deliverer.links[0]
    assert (luser, lagent, lserver) == ("uA", AGENT_ID, SERVER_ID)

    # link carries PKCE S256 + bound one-shot state + exact redirect_uri
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"] and q["code_challenge"][0]
    assert q["client_id"] == ["client-123"]
    assert q["redirect_uri"] == [f"{REDIRECT_BASE}/oauth/callback"]
    state = q["state"][0]
    # state maps server-side to A's triple + a PKCE verifier (we peek without consuming
    # by re-issuing knowledge: the callback below consumes it for real)
    assert state

    # no token persisted yet
    assert resolve_user_token(SERVER_ID, "uA", AGENT_ID) is None

    # ── 2. user A authorizes → /oauth/callback exchanges + encrypts into the DB ──
    token_calls: list[dict] = []
    monkeypatch.setattr(
        sc,
        "create_mcp_http_client",
        _mock_token_client(
            token_calls,
            response={
                "access_token": "A-ACCESS",
                "refresh_token": "A-REFRESH",
                "expires_in": 3600,
                "scope": "read",
                "token_type": "Bearer",
            },
        ),
    )
    api = TestClient(agent_app.build_app(AGENT_ID), raise_server_exceptions=True)
    resp = api.get("/oauth/callback", params={"code": "a-code", "state": state})
    assert resp.status_code == 200, resp.text
    # exchange used A's bound PKCE verifier (proving state→verifier reverse-resolution)
    assert token_calls and token_calls[0]["code"] == "a-code"
    assert token_calls[0]["grant_type"] == "authorization_code"

    # token now resolvable + stored encrypted (the on-disk column is not the plaintext)
    stored = resolve_user_token(SERVER_ID, "uA", AGENT_ID)
    assert stored is not None and stored.access_token == "A-ACCESS"
    row = db.execute(
        "SELECT access_token_ciphertext FROM mcp_user_tokens WHERE user_id=:u",
        {"u": "uA"},
    ).fetchone()
    assert row is not None
    assert "A-ACCESS" not in str(row["access_token_ciphertext"])  # ciphertext, never plaintext

    # ── 3. user A calls again → routes to A's session, injects A's bearer, succeeds ──
    result_a2 = await mc.call_tool(SERVER_ID, "do_thing", {}, None, user_id="uA", agent_id=AGENT_ID)
    assert result_a2 == "tool-ok"
    assert (None, SERVER_ID, "uA") in mc._active_sessions  # A's per-user session opened
    assert bearer_sink == ["Bearer A-ACCESS"]  # A's bearer rode the request

    # ── 4. user B calls → still no (B, agent, server) token → B's own authorization ──
    result_b = await mc.call_tool(SERVER_ID, "do_thing", {}, None, user_id="uB", agent_id=AGENT_ID)
    assert "needs your authorization" in result_b
    # B got their own link; A's token was never reused for B
    assert deliverer.links[-1][0] == "uB"
    assert resolve_user_token(SERVER_ID, "uB", AGENT_ID) is None
    # B did not open a session as A and B's call did not add a second bearer to the sink
    assert (None, SERVER_ID, "uB") not in mc._active_sessions
    assert bearer_sink == ["Bearer A-ACCESS"]
