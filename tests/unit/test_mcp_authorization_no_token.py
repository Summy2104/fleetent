"""Unit tests for Group 6: no-token call_tool path triggers authorization (D8).

A per-user oauth call by a user with no valid ``(user, agent, server)`` token returns a
clear "needs authorization" result on the degrade chain (no raise / no hang) AND triggers
authorization-link delivery via the injectable seam; a user WITH a valid token executes
normally and never triggers authorization. Isolation (agent1 vs agent2, sender-keyed) is
asserted at the call_tool boundary. SDK sessions / token resolver / deliverer are stubbed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import UserToken


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, args: dict) -> Any:
        self.calls.append((name, args))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            structuredContent=None,
            isError=False,
        )


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    monkeypatch.setattr(mc, "_session_hosts", {})
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base("https://agent.internal")
    yield
    az.reset_oauth_state_store()
    az.set_authorization_link_deliverer(None)
    az.set_redirect_base(None)


def _per_user_server(sid: str = "puo") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
        authorization_endpoint="https://as.internal/authorize",
        client_id="client-123",
        scope="read",
        redirect_path="/oauth/callback",
    )


def _emitted_capture(monkeypatch):
    """Capture emit_authorization_link calls (so a session is never opened on no-token)."""
    emitted: list[tuple[str, str, str]] = []

    async def _fake_emit(server, user_id, agent_id):
        emitted.append((server.id, user_id, agent_id))
        return True

    monkeypatch.setattr(mc, "_emit_authorization_link", _fake_emit)
    return emitted


# ── 6.1: no token → needs-authorization result + trigger ─────────────────────────


async def test_no_token_returns_needs_auth_and_triggers(monkeypatch):
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    emitted = _emitted_capture(monkeypatch)

    async def _no_open(*a, **k):
        raise AssertionError("must not open a session when the user has no token")

    monkeypatch.setattr(mc, "_open_session_for", _no_open)

    out = await mc.call_tool("puo", "do", {}, user_id="uA", agent_id="ag1")

    assert "authoriz" in out.lower() or "授权" in out
    assert emitted == [("puo", "uA", "ag1")]


async def test_no_token_does_not_leak_link_into_result(monkeypatch):
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    _emitted_capture(monkeypatch)

    out = await mc.call_tool("puo", "do", {}, user_id="uA", agent_id="ag1")
    # The link is delivered out-of-band via DM, never embedded in the tool result (which
    # could reach a shared channel) — only the DM-sent notice appears.
    assert "https://" not in out
    assert "authorize" not in out  # no raw URL fragment leaked


async def test_valid_token_executes_no_trigger(monkeypatch):
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server
    monkeypatch.setattr(
        mc,
        "resolve_user_token",
        lambda *a, **k: UserToken("tok", None, None, "read"),
    )
    emitted = _emitted_capture(monkeypatch)

    sess = _FakeSession()

    async def _fake_open(srv, scope, user_id=None, *a, **k):
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    out = await mc.call_tool("puo", "do", {"x": 1}, user_id="uA", agent_id="ag1")
    assert out == "ok"
    assert sess.calls == [("do", {"x": 1})]
    assert emitted == []  # a valid token never triggers authorization


# ── 6.4: isolation — agent1 vs agent2, sender-keyed ──────────────────────────────


async def test_agent2_no_token_triggers_own_auth(monkeypatch):
    """agent1 has a token; agent2 does not → agent2 triggers its own authorization."""
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    def _resolve(server_id, user_id, agent_id=None):
        if agent_id == "ag1":
            return UserToken("tok-ag1", None, None, "read")
        return None

    monkeypatch.setattr(mc, "resolve_user_token", _resolve)
    emitted = _emitted_capture(monkeypatch)

    sess = _FakeSession()

    async def _fake_open(srv, scope, user_id=None, *a, **k):
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    out1 = await mc.call_tool("puo", "do", {}, user_id="uA", agent_id="ag1")
    out2 = await mc.call_tool("puo", "do", {}, user_id="uA", agent_id="ag2")

    assert out1 == "ok"  # agent1 reuses its token
    assert "authoriz" in out2.lower() or "授权" in out2
    assert emitted == [("puo", "uA", "ag2")]  # only agent2 triggered, never reused ag1


async def test_shared_channel_sender_b_triggers_own_auth(monkeypatch):
    """User A authorized; user B (same agent) has no token → B triggers its own auth."""
    server = _per_user_server("puo")
    mc._server_registry[(None, "puo")] = server

    def _resolve(server_id, user_id, agent_id=None):
        if user_id == "A":
            return UserToken("tok-A", None, None, "read")
        return None

    monkeypatch.setattr(mc, "resolve_user_token", _resolve)
    emitted = _emitted_capture(monkeypatch)

    sess = _FakeSession()

    async def _fake_open(srv, scope, user_id=None, *a, **k):
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    out_a = await mc.call_tool("puo", "do", {}, user_id="A", agent_id="ag1")
    out_b = await mc.call_tool("puo", "do", {}, user_id="B", agent_id="ag1")

    assert out_a == "ok"
    assert "authoriz" in out_b.lower() or "授权" in out_b
    assert emitted == [("puo", "B", "ag1")]  # B's own auth, never A's token reused
