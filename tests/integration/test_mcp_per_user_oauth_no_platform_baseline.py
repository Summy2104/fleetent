"""Group 9.3 — no-platform baseline for mcp-per-user-oauth2.

The architecture contract requires the agent to keep working with **no platform and no
platform tables present**. This change adds per-user OAuth seams; this module pins that it
did not regress that baseline:

(a) the agent's ASGI app builds + serves its core endpoints (``/health``, ``/oauth/callback``)
    with no platform wiring and no platform DB — and importing none of the per-user-oauth
    modules pulls in ``fleetent.platform``;
(b) non per-user-oauth MCP services (``none`` / ``api_key`` / ``client_credentials``) route
    through ``call_tool`` exactly as before — never touching the per-user token resolver or
    the authorization trigger (no token store consulted, no link emitted, no user keying);
(c) standalone wiring (``wire_standalone_oauth``) succeeds unconditionally with no platform.

The SDK transport + ClientSession are stubbed (no wire); the per-agent DB is tmp_path-backed
and migrated. Nothing here touches ``data/`` or imports platform.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
from fleetent.db import SQLiteDatabase
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import (
    InMemoryUserTokenStore,
    set_local_user_token_store,
)
from fleetent.integrations.mcp.standalone_callback import wire_standalone_oauth
from fleetent.integrations.mcp.standalone_token_store import StandaloneUserTokenStore
from fleetent.runtime import agent_app
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))


@pytest.fixture(autouse=True)
def _clean_seams(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    monkeypatch.setattr(mc, "_session_hosts", {})
    az.reset_oauth_state_store()
    yield
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    mc.set_token_refresher(None)
    set_local_user_token_store(InMemoryUserTokenStore())


def _migrated_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


class _FakeSession:
    """Minimal stand-in for the SDK ClientSession (no wire)."""

    async def initialize(self) -> Any:
        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="plain-ok")])


def _install_stub_sdk(monkeypatch) -> None:
    def fake_transport(*a: Any, **k: Any) -> Any:
        @contextlib.asynccontextmanager
        async def _cm():
            yield ("read", "write", None)

        return _cm()

    monkeypatch.setattr(mc, "streamable_http_client", fake_transport)
    monkeypatch.setattr(mc, "streamablehttp_client", fake_transport)
    monkeypatch.setattr(mc, "sse_client", fake_transport)
    monkeypatch.setattr(mc, "stdio_client", fake_transport)

    @contextlib.asynccontextmanager
    async def _session_cm(*a: Any, **k: Any):
        yield _FakeSession()

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm())


def _tripwire_per_user_paths(monkeypatch) -> dict[str, list]:
    """Make the per-user resolver / authorization trigger fail loudly if ever touched.

    A non per-user-oauth server MUST never consult the per-user token resolver or emit an
    authorization link. We replace both seams with tripwires that record (and would let the
    test assert) any call — so a plain server silently entering the per-user path is caught.
    """
    calls: dict[str, list] = {"resolve": [], "emit": []}

    def boom_resolve(*a: Any, **k: Any):
        calls["resolve"].append((a, k))
        raise AssertionError("non per-user server must not consult resolve_user_token")

    async def boom_emit(*a: Any, **k: Any):
        calls["emit"].append((a, k))
        raise AssertionError("non per-user server must not emit an authorization link")

    monkeypatch.setattr(mc, "resolve_user_token", boom_resolve)
    monkeypatch.setattr(mc, "_emit_authorization_link", boom_emit)
    return calls


# ── (a) the agent app builds + serves with no platform ────────────────────────────


def test_agent_app_builds_and_serves_without_platform(tmp_path):
    """The agent ASGI app boots + answers /health without any platform DB or wiring."""
    db = _migrated_db(tmp_path)
    # standalone oauth wiring (c): unconditional, no platform involved
    wire_standalone_oauth(StandaloneUserTokenStore(db))

    api = TestClient(agent_app.build_app("ag1"), raise_server_exceptions=True)
    health = api.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # The self-hosted callback endpoint exists and rejects an unknown state with 400 — no
    # platform, no login state, no token written.
    cb = api.get("/oauth/callback", params={"code": "x", "state": "never-issued"})
    assert cb.status_code == 400


def test_per_user_oauth_modules_do_not_import_platform():
    """Importing the per-user-oauth surface pulls in no ``fleetent.platform`` (no-platform safe).

    Run in a *fresh* interpreter so the assertion is real (this process may already have
    platform loaded from sibling tests). Importing the full change surface must not load any
    ``fleetent.platform`` submodule as a side effect — the agent runs where platform is absent.
    """
    import subprocess
    import sys

    code = (
        "import sys\n"
        "for m in ["
        "'fleetent.integrations.mcp.oauth_authcode',"
        "'fleetent.integrations.mcp.per_user_tokens',"
        "'fleetent.integrations.mcp.standalone_token_store',"
        "'fleetent.integrations.mcp.authorization',"
        "'fleetent.integrations.mcp.standalone_callback',"
        "'fleetent.integrations.mcp.client',"
        "]:\n"
        "    __import__(m)\n"
        "leaked = sorted(k for k in sys.modules if k.startswith('fleetent.platform'))\n"
        "assert not leaked, 'per-user-oauth import leaked platform: ' + repr(leaked)\n"
        "print('OK')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "OK" in proc.stdout


# ── (b) non per-user-oauth services route unchanged ───────────────────────────────


async def test_plain_no_auth_server_unchanged(monkeypatch):
    """An auth_type='none' http server routes through call_tool, never the per-user path."""
    _install_stub_sdk(monkeypatch)
    _tripwire_per_user_paths(monkeypatch)

    server = McpServerConfig(id="plain", transport="http", url="https://host/mcp")
    mc._server_registry[(None, "plain")] = server

    out = await mc.call_tool("plain", "do", {}, None, user_id="uA", agent_id="ag1")
    assert out == "plain-ok"
    # plain server keyed without a user dimension (back-compat)
    assert (None, "plain") in mc._active_sessions
    assert (None, "plain", "uA") not in mc._active_sessions


async def test_api_key_server_unchanged(monkeypatch):
    """An api_key http server routes unchanged; the per-user resolver is never consulted."""
    monkeypatch.setenv("PLAIN_KEY", "secret-key")
    _install_stub_sdk(monkeypatch)
    _tripwire_per_user_paths(monkeypatch)

    server = McpServerConfig(
        id="ak",
        transport="http",
        url="https://host/mcp",
        auth_type="api_key",
        api_key_env="PLAIN_KEY",
    )
    mc._server_registry[(None, "ak")] = server

    out = await mc.call_tool("ak", "do", {}, None, user_id="uA", agent_id="ag1")
    assert out == "plain-ok"
    assert (None, "ak") in mc._active_sessions


async def test_client_credentials_server_unchanged(monkeypatch):
    """A client_credentials oauth server keeps the legacy (scope, server) keying + auth.

    It is oauth2 but NOT authorization_code, so it must not enter the per-user path: no user
    keying, no per-user resolver, no authorization trigger.
    """
    monkeypatch.setenv("CC_SECRET", "shh")
    _install_stub_sdk(monkeypatch)
    _tripwire_per_user_paths(monkeypatch)

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

    out = await mc.call_tool("cc", "do", {}, None, user_id="uA", agent_id="ag1")
    assert out == "plain-ok"
    # legacy 2-tuple keying preserved (no user dimension) for client_credentials
    assert (None, "cc") in mc._active_sessions
    assert (None, "cc", "uA") not in mc._active_sessions


# ── (c) standalone wiring holds with no platform ──────────────────────────────────


def test_wire_standalone_oauth_succeeds_without_platform(tmp_path):
    """wire_standalone_oauth installs the local store + refresher with no platform present."""
    db = _migrated_db(tmp_path)
    wire_standalone_oauth(StandaloneUserTokenStore(db))
    # the transparent refresher seam is now wired (standalone), no resolver injected
    assert mc.get_token_refresher() is not None
