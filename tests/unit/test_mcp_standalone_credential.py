"""Unit tests for Group 3 (3.3/3.4): standalone credential-form handler.

Covers ``integrations/mcp/standalone_credential``: identity reverse-resolved from the
one-shot ``state`` alone (never a login state); a valid submit stores the key under the
triple as ``credential_kind="static"``; unknown / expired / already-used state or a missing
key is rejected with no write; the rendered form embeds the state and never echoes a key.
In-memory state store + token store + a registered fake server — no FastAPI / real DB.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import fleetent.integrations.mcp.authorization as az
import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.per_user_tokens import InMemoryUserTokenStore
from fleetent.integrations.mcp.standalone_credential import (
    handle_credential_submit,
    render_credential_form,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    az.reset_oauth_state_store()
    yield
    az.reset_oauth_state_store()


def _register(sid: str = "acme") -> None:
    mc._server_registry[(None, sid)] = SimpleNamespace(id=sid, auth_type="api_key_per_user")


def test_valid_submit_stores_static_credential():
    _register("acme")
    store = InMemoryUserTokenStore()
    state = az.get_oauth_state_store().issue("uA", "ag1", "acme", "")

    result = handle_credential_submit(state=state, key="my-secret-key", store=store)

    assert result.ok and result.status == "stored"
    tok = store.get("uA", "ag1", "acme")
    assert tok is not None and tok.access_token == "my-secret-key"
    # static credential: no refresh/expiry/scope
    assert tok.refresh_token is None and tok.expires_at is None


def test_static_kind_passed_to_store():
    _register("acme")
    captured: dict = {}

    class _RecordingStore(InMemoryUserTokenStore):
        def put(self, user_id, agent_id, server_id, token, credential_kind="oauth"):
            captured["kind"] = credential_kind
            super().put(user_id, agent_id, server_id, token)

    state = az.get_oauth_state_store().issue("uA", "ag1", "acme", "")
    handle_credential_submit(state=state, key="k", store=_RecordingStore())
    assert captured["kind"] == "static"


def test_unknown_state_rejected_no_write():
    _register("acme")
    store = InMemoryUserTokenStore()
    result = handle_credential_submit(state="bogus", key="k", store=store)
    assert not result.ok and result.status == "invalid_state"
    assert store.get("uA", "ag1", "acme") is None


def test_consumed_state_rejected_second_time():
    _register("acme")
    store = InMemoryUserTokenStore()
    state = az.get_oauth_state_store().issue("uA", "ag1", "acme", "")
    assert handle_credential_submit(state=state, key="k1", store=store).ok
    second = handle_credential_submit(state=state, key="k2", store=store)
    assert not second.ok and second.status == "invalid_state"
    # the key from the first (valid) submit is untouched by the rejected second
    assert store.get("uA", "ag1", "acme").access_token == "k1"


def test_missing_key_rejected():
    _register("acme")
    store = InMemoryUserTokenStore()
    state = az.get_oauth_state_store().issue("uA", "ag1", "acme", "")
    result = handle_credential_submit(state=state, key="", store=store)
    assert not result.ok and result.status == "invalid_input"
    # the state is not consumed by an empty submit (user can retry)
    assert store.get("uA", "ag1", "acme") is None


def test_unknown_server_rejected():
    store = InMemoryUserTokenStore()
    state = az.get_oauth_state_store().issue("uA", "ag1", "ghost", "")
    result = handle_credential_submit(state=state, key="k", store=store)
    assert not result.ok and result.status == "unknown_server"


def test_form_embeds_state_and_never_echoes_key():
    html = render_credential_form("st-xyz")
    assert "st-xyz" in html  # state carried as a hidden field
    assert "<form" in html.lower()
    assert "password" in html.lower()  # the key input is masked
