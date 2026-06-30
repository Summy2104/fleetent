"""Unit tests for Group 3: per-user api-key credential-submission link + state + delivery.

Covers ``integrations/mcp/credential_submission``: a secure-form link whose one-shot
``state`` (reusing the OAuth slice's shared state store) is bound to (user, agent, server),
the form-URL assembly off the shared public base, and best-effort DM delivery through the
shared deliverer seam. No real wire / DB / FastAPI — store and deliverer are injected.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.credential_submission as cs
from fleetent.integrations.mcp.oauth_authcode import InMemoryStateStore


def _server(sid: str = "acme") -> SimpleNamespace:
    return SimpleNamespace(id=sid)


@pytest.fixture(autouse=True)
def _reset_seams():
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base(None)
    cs.set_credential_link_deliverer(None)
    yield
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base(None)
    cs.set_credential_link_deliverer(None)


# ── form-URI assembly (shared base) ───────────────────────────────────────────────


def test_form_uri_combines_base_and_path():
    az.set_redirect_base("https://agent.internal")
    url = cs.credential_form_uri("st-1")
    assert url == "https://agent.internal/mcp/credential?state=st-1"


def test_form_uri_handles_trailing_slash_base():
    az.set_redirect_base("https://agent.internal/")
    assert cs.credential_form_uri("st-1") == "https://agent.internal/mcp/credential?state=st-1"


def test_form_uri_falls_back_to_path_without_base():
    az.set_redirect_base(None)
    assert cs.credential_form_uri("st-1") == "/mcp/credential?state=st-1"


# ── build_credential_link: state bound to triple, no PKCE ─────────────────────────


def test_build_link_state_bound_to_user_agent_server():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    az.set_redirect_base("https://agent.internal")
    url = cs.build_credential_link(_server("srvX"), user_id="uA", agent_id="ag1")
    state = parse_qs(urlparse(url).query)["state"][0]
    bound = store.consume(state)
    assert bound is not None
    assert (bound.user_id, bound.agent_id, bound.server_id) == ("uA", "ag1", "srvX")
    # api-key has no PKCE; the verifier field is unused (empty) for credentials.
    assert bound.verifier == ""


def test_build_link_one_shot_state():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    url = cs.build_credential_link(_server(), user_id="uA", agent_id="ag1")
    state = parse_qs(urlparse(url).query)["state"][0]
    assert store.consume(state) is not None
    assert store.consume(state) is None  # second consume rejected (one-shot)


def test_build_link_distinct_state_per_call():
    url1 = cs.build_credential_link(_server(), user_id="uA", agent_id="ag1")
    url2 = cs.build_credential_link(_server(), user_id="uA", agent_id="ag1")
    s1 = parse_qs(urlparse(url1).query)["state"][0]
    s2 = parse_qs(urlparse(url2).query)["state"][0]
    assert s1 != s2


def test_state_isolated_by_sender_user_id():
    store = InMemoryStateStore()
    az.set_oauth_state_store(store)
    ua = cs.build_credential_link(_server("s"), user_id="A", agent_id="ag1")
    ub = cs.build_credential_link(_server("s"), user_id="B", agent_id="ag1")
    ba = store.consume(parse_qs(urlparse(ua).query)["state"][0])
    bb = store.consume(parse_qs(urlparse(ub).query)["state"][0])
    assert ba is not None and bb is not None
    assert ba.user_id == "A" and bb.user_id == "B"


# ── emit: best-effort DM delivery via the shared deliverer (Group 3.5) ─────────────


async def test_emit_invokes_deliverer_with_form_url():
    captured: dict[str, str] = {}

    async def _deliver(user_id, agent_id, server_id, url):
        captured.update(user_id=user_id, agent_id=agent_id, server_id=server_id, url=url)
        return True

    az.set_redirect_base("https://agent.internal")
    cs.set_credential_link_deliverer(_deliver)
    ok = await cs.emit_credential_link(_server("srvY"), "uA", "ag1")
    assert ok is True
    assert captured["server_id"] == "srvY"
    assert captured["url"].startswith("https://agent.internal/mcp/credential?state=")


async def test_emit_no_deliverer_returns_false_no_raise():
    cs.set_credential_link_deliverer(None)
    assert await cs.emit_credential_link(_server(), "uA", "ag1") is False


async def test_emit_swallows_deliverer_exception():
    async def _boom(*a, **k):
        raise RuntimeError("connector down")

    cs.set_credential_link_deliverer(_boom)
    assert await cs.emit_credential_link(_server(), "uA", "ag1") is False
