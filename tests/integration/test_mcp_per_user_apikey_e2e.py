"""Standalone per-user api-key/bearer end-to-end (http transport, mcp-per-user-apikey).

Ties Groups 2.5–3 together over a single per-user api-key http MCP service, with the SDK
session stubbed (no network / no real ``data/`` file):

1. user A's first call → no ``(A, agent, server)`` key → a clear "needs credential" result
   on the degrade chain (never an exception), and a secure-form link captured via the
   injected deliverer (DM) carrying a one-shot ``state`` and pointing at ``/mcp/credential``.
2. user A submits the form → drive ``POST /mcp/credential`` (FastAPI TestClient) with that
   state + a key → the key is persisted *encrypted* (``credential_kind=static``) in a
   tmp_path-backed, migrated ``agent_state.db``; the key never appears in the response.
3. user A calls again → the key resolves and the call executes as A: the per-user http
   session injects A's key under the configured ``header_style`` (here ``X-API-Key``).
4. user B calls the same service → still no key → B's own credential trigger; A's key is
   never reused for B.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
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
SERVER_ID = "acme"
REDIRECT_BASE = "https://agent.internal"


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))


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
    set_local_user_token_store(InMemoryUserTokenStore())


def _migrated_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _apikey_server() -> McpServerConfig:
    return McpServerConfig(
        id=SERVER_ID,
        transport="http",
        url="https://host/mcp",
        auth_type="api_key_per_user",
        header_style="x_api_key",
        credential_input="form",
    )


class _CapturingDeliverer:
    def __init__(self) -> None:
        self.links: list[tuple[str, str, str, str]] = []

    async def __call__(self, user_id: str, agent_id: str, server_id: str, url: str) -> bool:
        self.links.append((user_id, agent_id, server_id, url))
        return True


class _SpySession:
    """Stub SDK ClientSession that records the headers the bound auth would inject."""

    def __init__(self, http_client: httpx.AsyncClient | None, sink: list[dict[str, str]]) -> None:
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
            self._sink.append(dict(sent.headers))
        else:
            self._sink.append({})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="tool-ok")])


def _stub_sdk_transport(monkeypatch, header_sink: list[dict[str, str]]) -> None:
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
        yield _SpySession(holder.get("http_client"), header_sink)

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))


async def test_standalone_per_user_apikey_http_end_to_end(monkeypatch, tmp_path):
    db = _migrated_db(tmp_path)
    set_local_user_token_store(StandaloneUserTokenStore(db))
    mc._server_registry[(None, SERVER_ID)] = _apikey_server()

    deliverer = _CapturingDeliverer()
    az.set_authorization_link_deliverer(deliverer)

    header_sink: list[dict[str, str]] = []
    _stub_sdk_transport(monkeypatch, header_sink)

    # ── 1. user A's first call → needs-credential (no exception), form link captured ──
    result_a1 = await mc.call_tool(SERVER_ID, "do", {}, None, user_id="uA", agent_id=AGENT_ID)
    assert "needs your api-key/credential" in result_a1
    assert "https://" not in result_a1  # the link is DM'd, not embedded
    assert len(deliverer.links) == 1
    luser, lagent, lserver, url = deliverer.links[0]
    assert (luser, lagent, lserver) == ("uA", AGENT_ID, SERVER_ID)
    assert url.startswith(f"{REDIRECT_BASE}/mcp/credential?state=")
    state = parse_qs(urlparse(url).query)["state"][0]
    assert resolve_user_token(SERVER_ID, "uA", AGENT_ID) is None  # nothing stored yet

    # ── 2. user A submits the form → POST /mcp/credential stores encrypted static key ──
    api = TestClient(agent_app.build_app(AGENT_ID), raise_server_exceptions=True)
    resp = api.post("/mcp/credential", data={"state": state, "key": "A-KEY"})
    assert resp.status_code == 200, resp.text
    assert "A-KEY" not in resp.text  # the key is never echoed back

    stored = resolve_user_token(SERVER_ID, "uA", AGENT_ID)
    assert stored is not None and stored.access_token == "A-KEY"
    row = db.execute(
        "SELECT access_token_ciphertext, credential_kind FROM mcp_user_tokens WHERE user_id=:u",
        {"u": "uA"},
    ).fetchone()
    assert "A-KEY" not in str(row["access_token_ciphertext"])  # ciphertext, never plaintext
    assert row["credential_kind"] == "static"

    # re-submitting the same one-shot state is rejected (no second write path)
    resp2 = api.post("/mcp/credential", data={"state": state, "key": "EVIL"})
    assert resp2.status_code == 400

    # ── 3. user A calls again → key resolves, injected under header_style=x_api_key ──
    result_a2 = await mc.call_tool(SERVER_ID, "do", {}, None, user_id="uA", agent_id=AGENT_ID)
    assert result_a2 == "tool-ok"
    assert (None, SERVER_ID, "uA") in mc._active_sessions
    assert header_sink[-1].get("x-api-key") == "A-KEY"
    assert "authorization" not in header_sink[-1]  # x_api_key path, not Bearer

    # ── 4. user B calls → no key → B's own credential trigger; A's key never reused ──
    result_b = await mc.call_tool(SERVER_ID, "do", {}, None, user_id="uB", agent_id=AGENT_ID)
    assert "needs your api-key/credential" in result_b
    assert deliverer.links[-1][0] == "uB"
    assert resolve_user_token(SERVER_ID, "uB", AGENT_ID) is None
    assert (None, SERVER_ID, "uB") not in mc._active_sessions
