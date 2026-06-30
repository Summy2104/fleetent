"""Unit: per-user api-key/bearer recognition + header_style-aware http injection."""

from __future__ import annotations

import httpx

from fleetent.integrations.mcp import per_user_tokens
from fleetent.integrations.mcp.client import (
    McpServerConfig,
    _http_auth,
    _is_per_user_apikey,
    _is_per_user_credential,
    _session_key,
)


def _server(header_style: str = "bearer") -> McpServerConfig:
    return McpServerConfig(
        id="acme", transport="http", auth_type="api_key_per_user", header_style=header_style
    )


def _inject_first_header(auth: httpx.Auth) -> dict[str, str]:
    request = httpx.Request("POST", "https://acme/mcp")
    gen = auth.auth_flow(request)
    req = next(gen)
    return dict(req.headers)


def test_predicates_recognize_api_key_per_user():
    s = _server()
    assert _is_per_user_apikey(s)
    assert _is_per_user_credential(s)
    # per-user → session key gains the user dimension (3-tuple)
    assert _session_key(s, None, "u1") == (None, "acme", "u1")


def test_injects_bearer_by_default():
    server = _server("bearer")
    try:
        per_user_tokens.set_user_token_resolver(
            lambda sid, uid, aid: per_user_tokens.UserToken("the-key", None, None, None)
        )
        auth = _http_auth(server, "u1", "a1")
        assert auth is not None
        headers = _inject_first_header(auth)
        assert headers.get("authorization") == "Bearer the-key"
        assert "x-api-key" not in headers
    finally:
        per_user_tokens.set_user_token_resolver(None)


def test_injects_x_api_key_when_configured():
    server = _server("x_api_key")
    try:
        per_user_tokens.set_user_token_resolver(
            lambda sid, uid, aid: per_user_tokens.UserToken("the-key", None, None, None)
        )
        headers = _inject_first_header(_http_auth(server, "u1", "a1"))
        assert headers.get("x-api-key") == "the-key"
        assert "authorization" not in headers
    finally:
        per_user_tokens.set_user_token_resolver(None)


def test_no_key_injects_no_header():
    server = _server("bearer")
    try:
        per_user_tokens.set_user_token_resolver(lambda sid, uid, aid: None)
        headers = _inject_first_header(_http_auth(server, "u1", "a1"))
        assert "authorization" not in headers and "x-api-key" not in headers
    finally:
        per_user_tokens.set_user_token_resolver(None)
