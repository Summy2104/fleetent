"""Unit tests for the per-user MCP token storage abstraction + injection seam.

Pure abstraction / fallback / injection logic only — no real DB, no live resources.
Mirrors the ``set_im_identity_resolver`` seam pattern: module-level resolver=None +
setter + runtime resolution with a local fallback.
"""

from __future__ import annotations

import fleetent.integrations.mcp.per_user_tokens as put


def _token(access: str = "at", refresh: str | None = "rt") -> put.UserToken:
    return put.UserToken(
        access_token=access,
        refresh_token=refresh,
        expires_at=123.0,
        scope="read write",
    )


# ── token record dataclass ───────────────────────────────────────────────────────


def test_user_token_carries_oauth_fields():
    tok = put.UserToken(access_token="A", refresh_token="R", expires_at=42.0, scope="s")
    assert tok.access_token == "A"
    assert tok.refresh_token == "R"
    assert tok.expires_at == 42.0
    assert tok.scope == "s"


def test_user_token_allows_missing_refresh_and_expiry():
    tok = put.UserToken(access_token="A", refresh_token=None, expires_at=None, scope=None)
    assert tok.refresh_token is None
    assert tok.expires_at is None
    assert tok.scope is None


# ── in-memory store: triple isolation ─────────────────────────────────────────────


def test_inmemory_store_get_missing_returns_none():
    store = put.InMemoryUserTokenStore()
    assert store.get("u1", "a1", "s1") is None


def test_inmemory_store_put_then_get_round_trips():
    store = put.InMemoryUserTokenStore()
    store.put("u1", "a1", "s1", _token(access="X"))
    got = store.get("u1", "a1", "s1")
    assert got is not None
    assert got.access_token == "X"


def test_inmemory_store_triples_are_isolated():
    store = put.InMemoryUserTokenStore()
    store.put("u1", "a1", "s1", _token(access="for-u1"))
    # Differ in exactly one axis each — none must see u1/a1/s1's token.
    assert store.get("u2", "a1", "s1") is None  # different user
    assert store.get("u1", "a2", "s1") is None  # different agent
    assert store.get("u1", "a1", "s2") is None  # different server
    assert store.get("u1", "a1", "s1").access_token == "for-u1"


def test_inmemory_store_put_overwrites_same_triple():
    store = put.InMemoryUserTokenStore()
    store.put("u1", "a1", "s1", _token(access="old"))
    store.put("u1", "a1", "s1", _token(access="new"))
    assert store.get("u1", "a1", "s1").access_token == "new"


def test_inmemory_store_delete_only_affects_target_triple():
    store = put.InMemoryUserTokenStore()
    store.put("u1", "a1", "s1", _token())
    store.put("u1", "a1", "s2", _token())
    store.delete("u1", "a1", "s1")
    assert store.get("u1", "a1", "s1") is None
    assert store.get("u1", "a1", "s2") is not None


def test_inmemory_store_delete_missing_is_noop():
    store = put.InMemoryUserTokenStore()
    store.delete("u1", "a1", "s1")  # must not raise


# ── injection seam: set_user_token_resolver + resolve_user_token ──────────────────


def test_resolve_falls_back_to_local_store_when_unset(monkeypatch):
    # Ensure no resolver injected for this test.
    monkeypatch.setattr(put, "_resolver", None, raising=False)
    local = put.InMemoryUserTokenStore()
    monkeypatch.setattr(put, "_local_store", local, raising=False)
    local.put("u1", "a1", "s1", _token(access="local"))

    got = put.resolve_user_token("s1", "u1", "a1")
    assert got is not None
    assert got.access_token == "local"


def test_resolve_returns_none_when_local_has_no_token(monkeypatch):
    monkeypatch.setattr(put, "_resolver", None, raising=False)
    monkeypatch.setattr(put, "_local_store", put.InMemoryUserTokenStore(), raising=False)
    assert put.resolve_user_token("s1", "u1", "a1") is None


def test_resolve_uses_injected_resolver_when_set(monkeypatch):
    seen: list[tuple[str, str, str | None]] = []

    def fake_resolver(server_id: str, user_id: str, agent_id: str | None) -> put.UserToken | None:
        seen.append((server_id, user_id, agent_id))
        return _token(access="injected")

    monkeypatch.setattr(put, "_resolver", None, raising=False)
    put.set_user_token_resolver(fake_resolver)
    try:
        got = put.resolve_user_token("srv", "usr", "agt")
    finally:
        put.set_user_token_resolver(None)

    assert got is not None
    assert got.access_token == "injected"
    assert seen == [("srv", "usr", "agt")]


def test_injected_resolver_none_means_no_token(monkeypatch):
    monkeypatch.setattr(put, "_resolver", None, raising=False)
    put.set_user_token_resolver(lambda server_id, user_id, agent_id: None)
    try:
        assert put.resolve_user_token("srv", "usr", "agt") is None
    finally:
        put.set_user_token_resolver(None)


def test_resolve_agent_id_optional_defaults_none(monkeypatch):
    seen: list[str | None] = []

    def fake_resolver(server_id: str, user_id: str, agent_id: str | None) -> put.UserToken | None:
        seen.append(agent_id)
        return None

    monkeypatch.setattr(put, "_resolver", None, raising=False)
    put.set_user_token_resolver(fake_resolver)
    try:
        put.resolve_user_token("srv", "usr")
    finally:
        put.set_user_token_resolver(None)
    assert seen == [None]


def test_set_resolver_clears_with_none(monkeypatch):
    monkeypatch.setattr(put, "_resolver", None, raising=False)
    put.set_user_token_resolver(lambda *a: _token())
    put.set_user_token_resolver(None)
    # Cleared → falls back to local (empty) store → None.
    monkeypatch.setattr(put, "_local_store", put.InMemoryUserTokenStore(), raising=False)
    assert put.resolve_user_token("s", "u", "a") is None
