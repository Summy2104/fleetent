"""Unit tests for Group 6: no-token authorization trigger + link build + DM delivery.

Covers the per-user oauth authorization trigger seams in ``integrations/mcp/authorization``:
link generation (PKCE + state bound to user×agent×server, exact redirect_uri), the
injectable state-store + deliverer seams, and best-effort delivery. No real wire / DB /
FastAPI — the deliverer and state store are stubbed/injected.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import fleetent.integrations.mcp.authorization as az
from fleetent.integrations.mcp.oauth_authcode import InMemoryStateStore


def _server(sid: str = "puo") -> SimpleNamespace:
    return SimpleNamespace(
        id=sid,
        authorization_endpoint="https://as.internal/authorize",
        client_id="client-123",
        scope="read write",
        redirect_path="/oauth/callback",
    )


@pytest.fixture(autouse=True)
def _reset_seams():
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base(None)
    yield
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base(None)


# ── state store seam ────────────────────────────────────────────────────────────


def test_state_store_default_is_in_memory():
    assert isinstance(az.get_oauth_state_store(), InMemoryStateStore)


def test_set_oauth_state_store_injects_instance():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    assert az.get_oauth_state_store() is store


# ── redirect_uri assembly ───────────────────────────────────────────────────────


def test_redirect_uri_combines_base_and_path():
    az.set_redirect_base("https://agent.internal")
    assert az.redirect_uri_for(_server()) == "https://agent.internal/oauth/callback"


def test_redirect_uri_handles_trailing_slash_base():
    az.set_redirect_base("https://agent.internal/")
    assert az.redirect_uri_for(_server()) == "https://agent.internal/oauth/callback"


def test_redirect_uri_falls_back_to_path_without_base():
    az.set_redirect_base(None)
    assert az.redirect_uri_for(_server()) == "/oauth/callback"


def test_redirect_uri_reads_env(monkeypatch):
    az.set_redirect_base(None)
    monkeypatch.setenv("FLEETENT_OAUTH_REDIRECT_BASE", "https://env.internal")
    assert az.redirect_uri_for(_server()) == "https://env.internal/oauth/callback"


# ── build_authorization_link: PKCE + state bound to triple + exact redirect ──────


def test_build_link_has_pkce_and_state_and_response_type():
    az.set_redirect_base("https://agent.internal")
    url = az.build_authorization_link(_server(), user_id="uA", agent_id="ag1")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"]  # present and non-empty
    assert q["client_id"] == ["client-123"]
    assert q["scope"] == ["read write"]
    assert q["redirect_uri"] == ["https://agent.internal/oauth/callback"]
    assert q["state"]  # present


def test_build_link_state_bound_to_user_agent_server():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    url = az.build_authorization_link(_server("srvX"), user_id="uA", agent_id="ag1")
    state = parse_qs(urlparse(url).query)["state"][0]
    bound = store.consume(state)
    assert bound is not None
    assert (bound.user_id, bound.agent_id, bound.server_id) == ("uA", "ag1", "srvX")
    assert bound.verifier  # the PKCE verifier is carried server-side for the callback


def test_build_link_distinct_state_per_call():
    az.build_authorization_link  # noqa: B018 — readability
    url1 = az.build_authorization_link(_server(), user_id="uA", agent_id="ag1")
    url2 = az.build_authorization_link(_server(), user_id="uA", agent_id="ag1")
    s1 = parse_qs(urlparse(url1).query)["state"][0]
    s2 = parse_qs(urlparse(url2).query)["state"][0]
    assert s1 != s2  # one-shot, unguessable per call


# ── isolation: agent1 vs agent2, sender-keyed (6.4 link layer) ───────────────────


def test_state_isolated_by_agent_id():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    url1 = az.build_authorization_link(_server("s"), user_id="uA", agent_id="ag1")
    url2 = az.build_authorization_link(_server("s"), user_id="uA", agent_id="ag2")
    b1 = store.consume(parse_qs(urlparse(url1).query)["state"][0])
    b2 = store.consume(parse_qs(urlparse(url2).query)["state"][0])
    assert b1 is not None and b2 is not None
    assert b1.agent_id == "ag1" and b2.agent_id == "ag2"


def test_state_isolated_by_sender_user_id():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    url_a = az.build_authorization_link(_server("s"), user_id="A", agent_id="ag1")
    url_b = az.build_authorization_link(_server("s"), user_id="B", agent_id="ag1")
    ba = store.consume(parse_qs(urlparse(url_a).query)["state"][0])
    bb = store.consume(parse_qs(urlparse(url_b).query)["state"][0])
    assert ba is not None and bb is not None
    assert ba.user_id == "A" and bb.user_id == "B"


# ── deliverer seam ──────────────────────────────────────────────────────────────


async def test_emit_invokes_deliverer_with_url():
    captured: dict[str, str] = {}

    async def _deliver(user_id, agent_id, server_id, url):
        captured.update(user_id=user_id, agent_id=agent_id, server_id=server_id, url=url)
        return True

    az.set_authorization_link_deliverer(_deliver)
    ok = await az.emit_authorization_link(_server("srvY"), "uA", "ag1")
    assert ok is True
    assert captured["user_id"] == "uA"
    assert captured["agent_id"] == "ag1"
    assert captured["server_id"] == "srvY"
    assert captured["url"].startswith("https://as.internal/authorize")


async def test_emit_no_deliverer_returns_false_no_raise():
    az.set_authorization_link_deliverer(None)
    ok = await az.emit_authorization_link(_server(), "uA", "ag1")
    assert ok is False  # link still issued (state stored) but not delivered


async def test_emit_swallows_deliverer_exception():
    async def _boom(*a, **k):
        raise RuntimeError("connector down")

    az.set_authorization_link_deliverer(_boom)
    ok = await az.emit_authorization_link(_server(), "uA", "ag1")
    assert ok is False  # never propagates; call can still degrade gracefully


async def test_per_call_deliverer_takes_precedence_over_boot():
    calls: list[str] = []

    async def _boot(*a, **k):
        calls.append("boot")
        return True

    async def _per_call(*a, **k):
        calls.append("per_call")
        return True

    az.set_authorization_link_deliverer(_boot)
    token = az.bind_call_deliverer(_per_call)
    try:
        await az.emit_authorization_link(_server(), "uA", "ag1")
    finally:
        az.reset_call_deliverer(token)
    assert calls == ["per_call"]  # per-call wins while bound

    # After reset, the boot-level deliverer is back in effect.
    await az.emit_authorization_link(_server(), "uA", "ag1")
    assert calls == ["per_call", "boot"]
