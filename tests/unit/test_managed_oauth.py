"""Unit: agent-side managed per-user OAuth wiring (resolver cache + state store)."""

from __future__ import annotations

from types import SimpleNamespace

from fleetent.integrations.mcp import managed_oauth, per_user_tokens


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def test_resolver_fetches_caches_and_returns_access_only() -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _Resp(200, {"access_token": "AT-1"})

    clock = {"t": 1000.0}
    resolver = managed_oauth.ManagedUserTokenResolver(
        "http://127.0.0.1:8786", "alpha", "tui-tok", now=lambda: clock["t"], http_post=fake_post
    )

    tok = resolver("crm", "u1", "alpha")
    assert tok is not None
    assert tok.access_token == "AT-1"
    assert tok.refresh_token is None  # refresh token never leaves platform
    assert calls and calls[0][0].endswith("/agent/alpha/mcp/oauth-token")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer tui-tok"

    # Within TTL -> cache hit, no second network call
    again = resolver("crm", "u1", "alpha")
    assert again is not None and again.access_token == "AT-1"
    assert len(calls) == 1

    # After TTL -> refetch
    clock["t"] += 100.0
    resolver("crm", "u1", "alpha")
    assert len(calls) == 2


def test_resolver_returns_none_on_404() -> None:
    resolver = managed_oauth.ManagedUserTokenResolver(
        "http://127.0.0.1:8786", "alpha", "tui-tok", http_post=lambda url, **kw: _Resp(404)
    )
    assert resolver("crm", "u1", "alpha") is None


def test_state_store_issue_registers_pending_and_returns_state() -> None:
    posted = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs["json"]
        posted["headers"] = kwargs["headers"]
        return _Resp(200, {"ok": True})

    # McpServerConfig flattens oauth fields onto the server object.
    server = SimpleNamespace(
        id="crm",
        redirect_path="/oauth/callback",
        token_url="https://auth/token",
        client_id="cid",
        client_secret_env="CS",
    )
    store = managed_oauth.ManagedStateStore(
        "http://127.0.0.1:8786", "alpha", "tui-tok", lambda sid: server, http_post=fake_post
    )

    state = store.issue("u1", "alpha", "crm", "verifier-xyz")

    assert state and posted["url"].endswith("/agent/alpha/mcp/oauth-pending")
    assert posted["json"]["state"] == state
    assert posted["json"]["code_verifier"] == "verifier-xyz"
    assert posted["json"]["token_url"] == "https://auth/token"
    assert posted["json"]["client_id"] == "cid"
    assert posted["json"]["client_secret_env"] == "CS"
    assert posted["headers"]["Authorization"] == "Bearer tui-tok"
    # Platform consumes the state at its callback; the agent-side store never does.
    assert store.consume(state) is None


def test_wire_managed_oauth_injects_resolver_seam() -> None:
    try:
        managed_oauth.wire_managed_oauth(
            "http://127.0.0.1:8786", "alpha", "tui-tok", lambda sid: None
        )
        # The injected resolver now takes precedence over the local store.
        assert per_user_tokens._resolver is not None
    finally:
        per_user_tokens.set_user_token_resolver(None)
