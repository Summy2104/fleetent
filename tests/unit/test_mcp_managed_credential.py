"""Unit: managed per-user api-key credential pending registration via node loopback (4.3).

Under managed deployment the credential link build goes through the same ``ManagedStateStore``
as OAuth: ``issue`` posts the one-shot state→triple as a pending record to the node loopback
(``/agent/<name>/mcp/oauth-pending``), which forwards to platform — the agent never imports
platform nor addresses it directly. For an api-key server the OAuth-specific fields are empty.
The token fetch path is the OAuth one (``fetch_access_token`` serves static keys as-is), so no
new fetch wiring is needed. http_post is stubbed — no real wire.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.credential_submission as cs
from fleetent.integrations.mcp import per_user_tokens
from fleetent.integrations.mcp.managed_oauth import ManagedCredentialWriter, ManagedStateStore


@pytest.fixture(autouse=True)
def _reset_seams():
    az.reset_oauth_state_store()
    az.set_redirect_base(None)
    per_user_tokens.set_credential_writer(None)
    yield
    az.reset_oauth_state_store()
    az.set_redirect_base(None)
    per_user_tokens.set_credential_writer(None)


def _apikey_server(sid: str = "acme") -> SimpleNamespace:
    # An api-key server carries no OAuth config; ManagedStateStore reads these via getattr.
    return SimpleNamespace(
        id=sid, token_url="", client_id="", client_secret_env="", redirect_path=""
    )


def test_build_credential_link_registers_pending_via_loopback():
    posted: list[dict] = []

    def _post(url, **kw):
        posted.append({"url": url, "json": kw.get("json"), "headers": kw.get("headers")})
        return SimpleNamespace(status_code=200, json=lambda: {})

    store = ManagedStateStore(
        "http://127.0.0.1:8767",
        "my-bot",
        "tui-token",
        lambda sid: _apikey_server(sid),
        http_post=_post,
    )
    az.set_oauth_state_store(store)
    az.set_redirect_base("https://platform.internal")

    url = cs.build_credential_link(_apikey_server("acme"), user_id="uA", agent_id="ag1")

    # The credential form URL points at the (managed platform) form, carrying the state.
    assert url.startswith("https://platform.internal/mcp/credential?state=")
    # Exactly one pending registration, forwarded through the node loopback (not platform).
    assert len(posted) == 1
    p = posted[0]
    assert p["url"] == "http://127.0.0.1:8767/agent/my-bot/mcp/oauth-pending"
    assert p["headers"]["Authorization"] == "Bearer tui-token"
    body = p["json"]
    assert (body["user_id"], body["agent_id"], body["server_id"]) == ("uA", "ag1", "acme")
    # api-key submission: no PKCE / OAuth config in the pending record.
    assert body["code_verifier"] == ""
    assert body["token_url"] == "" and body["client_id"] == ""


def test_managed_consume_is_platform_side_only():
    # The agent-side managed state store never consumes (platform's endpoint does).
    store = ManagedStateStore(
        "http://127.0.0.1:8767",
        "my-bot",
        "tui-token",
        lambda sid: _apikey_server(sid),
        http_post=lambda url, **kw: SimpleNamespace(status_code=200, json=lambda: {}),
    )
    assert store.consume("anything") is None


# ── mode 2 (in-DM tool) managed write path: node loopback credential-set ──────────


def test_managed_credential_writer_posts_to_loopback():
    posted: list[dict] = []

    def _post(url, **kw):
        posted.append({"url": url, "json": kw.get("json"), "headers": kw.get("headers")})
        return SimpleNamespace(status_code=200)

    writer = ManagedCredentialWriter(
        "http://127.0.0.1:8767", "my-bot", "tui-token", http_post=_post
    )
    ok = writer("acme", "uA", "ag1", "the-key")
    assert ok is True
    assert len(posted) == 1
    p = posted[0]
    assert p["url"] == "http://127.0.0.1:8767/agent/my-bot/mcp/credential-set"
    assert p["headers"]["Authorization"] == "Bearer tui-token"
    assert p["json"] == {"user_id": "uA", "agent_id": "ag1", "server_id": "acme", "key": "the-key"}


def test_managed_writer_reports_failure_on_error_status():
    writer = ManagedCredentialWriter(
        "http://127.0.0.1:8767",
        "my-bot",
        "t",
        http_post=lambda url, **kw: SimpleNamespace(status_code=500),
    )
    assert writer("acme", "uA", "ag1", "k") is False


def test_store_user_credential_routes_through_injected_writer():
    calls: list[tuple] = []
    per_user_tokens.set_credential_writer(
        lambda sid, uid, aid, key: calls.append((sid, uid, aid, key)) or True
    )
    # Managed: the local store is never touched; the write goes through the writer seam.
    assert per_user_tokens.store_user_credential("acme", "uA", "ag1", "k") is True
    assert calls == [("acme", "uA", "ag1", "k")]
