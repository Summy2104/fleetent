"""Unit tests for the transport-/deployment-agnostic OAuth 2.1 Authorization Code
protocol logic module (``integrations.mcp.oauth_authcode``): PKCE (S256), authorization
URL assembly, injectable one-shot state store with TTL, and code-exchange / refresh
request construction + response parsing + auth-error classification.

Pure logic only — no real network, no DB, no FastAPI. The token endpoint is driven over
httpx.MockTransport (respx-style), never a real server."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import fleetent.integrations.mcp.oauth_authcode as oa

# ── PKCE (Task 1.1) ───────────────────────────────────────────────────────────


def test_generate_pkce_challenge_is_s256_of_verifier():
    pair = oa.generate_pkce()
    assert pair.method == "S256"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert pair.challenge == expected


def test_generate_pkce_verifier_length_and_charset():
    # RFC 7636: code_verifier is 43..128 chars from the unreserved set.
    pair = oa.generate_pkce()
    assert 43 <= len(pair.verifier) <= 128
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    assert set(pair.verifier) <= allowed


def test_generate_pkce_is_unpredictable():
    assert oa.generate_pkce().verifier != oa.generate_pkce().verifier


def test_verify_pkce_accepts_matching_pair():
    pair = oa.generate_pkce()
    assert oa.verify_pkce(pair.verifier, pair.challenge) is True


def test_verify_pkce_rejects_mismatched_pair():
    pair = oa.generate_pkce()
    other = oa.generate_pkce()
    assert oa.verify_pkce(pair.verifier, other.challenge) is False


# ── authorization URL assembly (Task 1.1) ─────────────────────────────────────


def test_build_authorization_url_contains_required_params():
    pair = oa.generate_pkce()
    url = oa.build_authorization_url(
        authorization_endpoint="https://auth.example/authorize",
        client_id="cid",
        redirect_uri="https://agent.example/oauth/callback",
        scope="read write",
        state="st-123",
        code_challenge=pair.challenge,
    )
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://auth.example/authorize"
    q = parse_qs(parsed.query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["https://agent.example/oauth/callback"]
    assert q["scope"] == ["read write"]
    assert q["state"] == ["st-123"]
    assert q["code_challenge"] == [pair.challenge]
    assert q["code_challenge_method"] == ["S256"]


def test_build_authorization_url_preserves_existing_query():
    url = oa.build_authorization_url(
        authorization_endpoint="https://auth.example/authorize?audience=api",
        client_id="cid",
        redirect_uri="https://agent.example/cb",
        scope="",
        state="st",
        code_challenge="ch",
    )
    q = parse_qs(urlparse(url).query)
    assert q["audience"] == ["api"]
    assert q["response_type"] == ["code"]


def test_build_authorization_url_omits_empty_scope():
    url = oa.build_authorization_url(
        authorization_endpoint="https://auth.example/authorize",
        client_id="cid",
        redirect_uri="https://agent.example/cb",
        scope="",
        state="st",
        code_challenge="ch",
    )
    assert "scope=" not in urlparse(url).query


# ── state management (Task 1.2) ───────────────────────────────────────────────


def test_issue_state_is_unpredictable_and_bound():
    store = oa.InMemoryStateStore()
    pair = oa.generate_pkce()
    s1 = store.issue("u1", "a1", "srv1", pair.verifier)
    s2 = store.issue("u1", "a1", "srv1", pair.verifier)
    assert s1 != s2
    assert len(s1) >= 32


def test_consume_returns_bound_tuple_then_invalidates():
    store = oa.InMemoryStateStore()
    pair = oa.generate_pkce()
    state = store.issue("u1", "a1", "srv1", pair.verifier)
    consumed = store.consume(state)
    assert consumed is not None
    assert consumed.user_id == "u1"
    assert consumed.agent_id == "a1"
    assert consumed.server_id == "srv1"
    assert consumed.verifier == pair.verifier
    # one-shot: a second consume is rejected
    assert store.consume(state) is None


def test_consume_unknown_state_rejected():
    store = oa.InMemoryStateStore()
    assert store.consume("never-issued") is None


def test_consume_expired_state_rejected():
    now = {"t": 1000.0}
    store = oa.InMemoryStateStore(ttl_seconds=300.0, clock=lambda: now["t"])
    state = store.issue("u", "a", "s", "verifier")
    now["t"] = 1000.0 + 301.0  # past TTL
    assert store.consume(state) is None


def test_consume_within_ttl_accepted():
    now = {"t": 1000.0}
    store = oa.InMemoryStateStore(ttl_seconds=300.0, clock=lambda: now["t"])
    state = store.issue("u", "a", "s", "verifier")
    now["t"] = 1000.0 + 299.0
    assert store.consume(state) is not None


def test_state_store_no_module_level_mutable_global():
    # Two independent stores must not share state.
    a = oa.InMemoryStateStore()
    b = oa.InMemoryStateStore()
    state = a.issue("u", "ag", "sv", "v")
    assert b.consume(state) is None
    assert a.consume(state) is not None


# ── code exchange (Task 1.3) ──────────────────────────────────────────────────


def _token_handler(captured: dict, *, json_body: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(status, json=json_body, request=request)

    return handler


async def test_exchange_code_builds_request_and_parses_token():
    captured: dict = {}
    handler = _token_handler(
        captured,
        json_body={
            "access_token": "AT-1",
            "refresh_token": "RT-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
        },
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await oa.exchange_code(
            token_url="https://auth.example/oauth/token",
            client_id="cid",
            client_secret="shh",
            code="the-code",
            code_verifier="the-verifier",
            redirect_uri="https://agent.example/cb",
            http_client=client,
            now=lambda: 1000.0,
        )
    assert result.access_token == "AT-1"
    assert result.refresh_token == "RT-1"
    assert result.scope == "read write"
    assert result.expires_at == 1000.0 + 3600
    # client_secret_post + authorization_code grant
    body = parse_qs(captured["body"])
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["the-code"]
    assert body["code_verifier"] == ["the-verifier"]
    assert body["redirect_uri"] == ["https://agent.example/cb"]
    assert body["client_id"] == ["cid"]
    assert body["client_secret"] == ["shh"]
    assert "x-www-form-urlencoded" in captured["content_type"]


async def test_exchange_code_handles_missing_expires_in():
    handler = _token_handler(
        {},
        json_body={"access_token": "AT", "token_type": "Bearer"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await oa.exchange_code(
            token_url="https://auth.example/oauth/token",
            client_id="cid",
            client_secret="shh",
            code="c",
            code_verifier="v",
            redirect_uri="https://a/cb",
            http_client=client,
        )
    assert result.access_token == "AT"
    assert result.refresh_token is None
    assert result.expires_at is None


async def test_exchange_code_genuine_auth_error_raises_unavailable():
    handler = _token_handler({}, json_body={"error": "invalid_grant"}, status=400)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(oa.OAuthAuthError):
            await oa.exchange_code(
                token_url="https://auth.example/oauth/token",
                client_id="cid",
                client_secret="shh",
                code="c",
                code_verifier="v",
                redirect_uri="https://a/cb",
                http_client=client,
            )


async def test_exchange_code_transient_error_raises_transient():
    handler = _token_handler({}, json_body={"error": "server_error"}, status=503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(oa.OAuthTransientError):
            await oa.exchange_code(
                token_url="https://auth.example/oauth/token",
                client_id="cid",
                client_secret="shh",
                code="c",
                code_verifier="v",
                redirect_uri="https://a/cb",
                http_client=client,
            )


# ── refresh (Task 1.3) ────────────────────────────────────────────────────────


async def test_refresh_token_builds_request_and_parses():
    captured: dict = {}
    handler = _token_handler(
        captured,
        json_body={
            "access_token": "AT-2",
            "refresh_token": "RT-2",
            "token_type": "Bearer",
            "expires_in": 1800,
        },
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await oa.refresh_token(
            token_url="https://auth.example/oauth/token",
            client_id="cid",
            client_secret="shh",
            refresh_token="RT-1",
            http_client=client,
            now=lambda: 2000.0,
        )
    assert result.access_token == "AT-2"
    assert result.refresh_token == "RT-2"
    assert result.expires_at == 2000.0 + 1800
    body = parse_qs(captured["body"])
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["RT-1"]
    assert body["client_id"] == ["cid"]
    assert body["client_secret"] == ["shh"]


async def test_refresh_token_keeps_old_refresh_when_omitted():
    handler = _token_handler(
        {},
        json_body={"access_token": "AT-2", "token_type": "Bearer", "expires_in": 60},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await oa.refresh_token(
            token_url="https://auth.example/oauth/token",
            client_id="cid",
            client_secret="shh",
            refresh_token="RT-keep",
            http_client=client,
        )
    # When the AS does not rotate refresh tokens, the caller keeps using the old one.
    assert result.refresh_token == "RT-keep"


async def test_refresh_token_genuine_auth_error_raises_unavailable():
    handler = _token_handler({}, json_body={"error": "invalid_grant"}, status=400)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(oa.OAuthAuthError):
            await oa.refresh_token(
                token_url="https://auth.example/oauth/token",
                client_id="cid",
                client_secret="shh",
                refresh_token="RT-bad",
                http_client=client,
            )


# ── error classification (Task 1.3) ───────────────────────────────────────────


def _resp(status: int, *, json=None, text: str = "") -> httpx.Response:
    req = httpx.Request("POST", "https://auth.example/oauth/token")
    if json is not None:
        return httpx.Response(status, json=json, request=req)
    return httpx.Response(status, text=text, request=req)


def test_is_auth_error_401():
    assert oa.is_auth_error_response(_resp(401)) is True


def test_is_auth_error_invalid_client_and_grant():
    assert oa.is_auth_error_response(_resp(400, json={"error": "invalid_client"})) is True
    assert oa.is_auth_error_response(_resp(400, json={"error": "invalid_grant"})) is True
    assert oa.is_auth_error_response(_resp(403, json={"error": "unauthorized_client"})) is True


def test_is_auth_error_transient_5xx_is_not_auth():
    assert oa.is_auth_error_response(_resp(503, text="down")) is False


def test_is_auth_error_non_credential_4xx_is_not_auth():
    assert oa.is_auth_error_response(_resp(400, json={"error": "server_error"})) is False
