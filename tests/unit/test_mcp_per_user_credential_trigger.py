"""Unit tests for Group 2.5: no-key per-user api-key call triggers credential submission.

A per-user api-key/bearer call by a user with no stored ``(user, agent, server)`` key
returns a clear "needs credential" result on the degrade chain (no raise / no hang) AND,
per the server's ``credential_input``, triggers the secure-form link delivery (form / both)
or guides the user to the in-DM tool (tool-only). A user WITH a stored key executes
normally and never triggers submission. SDK sessions / token resolver / deliverer stubbed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

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


def _apikey_server(sid: str = "acme", credential_input: str = "form") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="api_key_per_user",
        header_style="bearer",
        credential_input=credential_input,
    )


def _emit_capture(monkeypatch):
    """Capture emit_credential_link calls (so no session is opened on a no-key call)."""
    emitted: list[tuple[str, str, str]] = []

    async def _fake_emit(server, user_id, agent_id):
        emitted.append((server.id, user_id, agent_id))
        return True

    monkeypatch.setattr(mc, "_emit_credential_link", _fake_emit)
    return emitted


async def test_no_key_returns_needs_credential_and_triggers_form(monkeypatch):
    server = _apikey_server("acme", "form")
    mc._server_registry[(None, "acme")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    emitted = _emit_capture(monkeypatch)

    async def _no_open(*a, **k):
        raise AssertionError("must not open a session when the user has no key")

    monkeypatch.setattr(mc, "_open_session_for", _no_open)

    out = await mc.call_tool("acme", "do", {}, user_id="uA", agent_id="ag1")

    assert "credential" in out.lower() or "key" in out.lower() or "凭据" in out
    assert emitted == [("acme", "uA", "ag1")]


async def test_no_key_does_not_leak_link_into_result(monkeypatch):
    server = _apikey_server("acme", "form")
    mc._server_registry[(None, "acme")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    _emit_capture(monkeypatch)

    out = await mc.call_tool("acme", "do", {}, user_id="uA", agent_id="ag1")
    # The submission link is delivered out-of-band via DM, never embedded in the result.
    assert "https://" not in out


async def test_tool_only_does_not_emit_form_link(monkeypatch):
    server = _apikey_server("acme", "tool")
    mc._server_registry[(None, "acme")] = server
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    emitted = _emit_capture(monkeypatch)

    async def _no_open(*a, **k):
        raise AssertionError("must not open a session when the user has no key")

    monkeypatch.setattr(mc, "_open_session_for", _no_open)

    out = await mc.call_tool("acme", "do", {}, user_id="uA", agent_id="ag1")
    # tool-only: no secure-form link is emitted; the user is guided to the in-DM tool.
    assert emitted == []
    assert "set_mcp_credential" in out or "dm" in out.lower() or "私信" in out


async def test_valid_key_executes_no_trigger(monkeypatch):
    server = _apikey_server("acme", "form")
    mc._server_registry[(None, "acme")] = server
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("the-key", None, None, None)
    )
    emitted = _emit_capture(monkeypatch)

    sess = _FakeSession()

    async def _fake_open(srv, scope, user_id=None, *a, **k):
        mc._active_sessions[mc._session_key(srv, scope, user_id)] = sess
        return sess

    monkeypatch.setattr(mc, "_open_session_for", _fake_open)

    out = await mc.call_tool("acme", "do", {"x": 1}, user_id="uA", agent_id="ag1")
    assert out == "ok"
    assert sess.calls == [("do", {"x": 1})]
    assert emitted == []  # a stored key never triggers submission
