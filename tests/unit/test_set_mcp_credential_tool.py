"""Unit tests for Group 5: the DM-gated ``set_mcp_credential`` tool (mode 2, opt-in).

The tool accepts a user-supplied api-key only for a per-user api-key server whose
``credential_input`` allows it (tool / both) AND only in a private DM (a channel call is
refused and guided to DM / the secure form). A form-only server makes the tool unavailable.
A successful DM submit stores the key under the (user, agent, server) triple as a static
credential. The key argument is auto-redacted from the trace (sensitive arg name). Storage
uses the local per-user store (standalone) via the credential-writer seam — stubbed here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.eval_logger import _redact_tool_call
from fleetent.integrations.mcp import per_user_tokens
from fleetent.integrations.mcp.per_user_tokens import InMemoryUserTokenStore
from fleetent.tools.builtin_tools import set_mcp_credential
from fleetent.tools.registry import ToolContext


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    per_user_tokens.set_credential_writer(None)
    per_user_tokens.set_local_user_token_store(InMemoryUserTokenStore())
    yield
    per_user_tokens.set_credential_writer(None)
    per_user_tokens.set_local_user_token_store(InMemoryUserTokenStore())


def _register(sid: str, credential_input: str = "tool") -> None:
    mc._server_registry[(None, sid)] = SimpleNamespace(
        id=sid, auth_type="api_key_per_user", credential_input=credential_input
    )


def _ctx(chat_type: str = "dm", user_id: str = "uA", agent_name: str = "ag1") -> ToolContext:
    return ToolContext(
        agent_name=agent_name,
        session_context=SimpleNamespace(chat_type=chat_type),
        principal=SimpleNamespace(user_id=user_id),
    )


def test_dm_submit_stores_credential():
    _register("acme", "tool")
    store = InMemoryUserTokenStore()
    per_user_tokens.set_local_user_token_store(store)

    out = set_mcp_credential("acme", "my-secret", tool_context=_ctx("dm"))

    tok = store.get("uA", "ag1", "acme")
    assert tok is not None and tok.access_token == "my-secret"
    assert "my-secret" not in out  # never echo the key back
    assert "acme" in out


def test_channel_call_refused_and_guided():
    _register("acme", "tool")
    store = InMemoryUserTokenStore()
    per_user_tokens.set_local_user_token_store(store)

    out = set_mcp_credential("acme", "my-secret", tool_context=_ctx("channel"))

    assert "error" in out.lower() or "dm" in out.lower() or "私信" in out
    assert store.get("uA", "ag1", "acme") is None  # nothing stored from a channel


def test_form_only_server_makes_tool_unavailable():
    _register("acme", "form")  # default form-only
    out = set_mcp_credential("acme", "my-secret", tool_context=_ctx("dm"))
    assert "error" in out.lower()
    assert "form" in out.lower() or "表单" in out


def test_both_mode_allows_tool_in_dm():
    _register("acme", "both")
    store = InMemoryUserTokenStore()
    per_user_tokens.set_local_user_token_store(store)
    out = set_mcp_credential("acme", "k", tool_context=_ctx("dm"))
    assert store.get("uA", "ag1", "acme") is not None
    assert "error" not in out.lower()


def test_unknown_or_non_apikey_server_refused():
    mc._server_registry[(None, "oauthsrv")] = SimpleNamespace(
        id="oauthsrv", auth_type="oauth2", credential_input="tool"
    )
    out = set_mcp_credential("oauthsrv", "k", tool_context=_ctx("dm"))
    assert "error" in out.lower()
    out2 = set_mcp_credential("ghost", "k", tool_context=_ctx("dm"))
    assert "error" in out2.lower()


def test_key_arg_is_redacted_in_trace():
    # The trace redaction keys off the *name* of the argument; "key" is sensitive.
    tc = {
        "function": {
            "name": "set_mcp_credential",
            "arguments": '{"server_id": "acme", "key": "super-secret"}',
        }
    }
    out = _redact_tool_call(tc)
    import json

    args = json.loads(out["function"]["arguments"])
    assert args["server_id"] == "acme"
    assert args["key"] != "super-secret"  # redacted
