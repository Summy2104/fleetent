from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import RSAKey

from fleetent.platform.user_management.oidc import OidcAuthError, OidcRelyingParty, OidcSettings


def _private_key_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _jwks(private_key_pem: bytes) -> dict[str, object]:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key = RSAKey.import_key(public_pem, parameters={"kid": "test-key"}).as_dict()
    return {"keys": [public_key]}


def _id_token(
    private_key_pem: bytes,
    *,
    issuer: str = "https://idp.example.com/realms/acme",
    audience: str = "fleetent-web",
    nonce: str = "nonce-123",
    email: str | None = "person@example.com",
    email_verified: bool | None = True,
    issued_at: int | None = None,
    expires_at: int | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": "user-123",
        "aud": audience,
        "iat": issued_at if issued_at is not None else now - 10,
        "exp": expires_at if expires_at is not None else now + 300,
        "nonce": nonce,
    }
    if email is not None:
        payload["email"] = email
    if email_verified is not None:
        payload["email_verified"] = email_verified
    return jwt.encode(
        {"alg": "RS256", "kid": "test-key"},
        payload,
        RSAKey.import_key(private_key_pem, parameters={"kid": "test-key"}),
    )


@respx.mock
def test_build_authorize_url_uses_discovery_and_includes_state_nonce():
    settings = OidcSettings(
        issuer="https://idp.example.com/realms/acme",
        client_id="fleetent-web",
        redirect_uri="https://fleetent.example.com/admin/oidc/callback",
    )
    discovery = respx.get(
        "https://idp.example.com/realms/acme/.well-known/openid-configuration"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": settings.issuer,
                "authorization_endpoint": "https://idp.example.com/oauth2/authorize",
                "token_endpoint": "https://idp.example.com/oauth2/token",
                "jwks_uri": "https://idp.example.com/oauth2/jwks",
            },
        )
    )

    client = OidcRelyingParty(settings)

    url = client.build_authorize_url(state="state-123", nonce="nonce-456")
    params = parse_qs(urlparse(url).query)

    assert discovery.called
    assert url.startswith("https://idp.example.com/oauth2/authorize?")
    assert params["client_id"] == ["fleetent-web"]
    assert params["redirect_uri"] == ["https://fleetent.example.com/admin/oidc/callback"]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["openid email"]
    assert params["state"] == ["state-123"]
    assert params["nonce"] == ["nonce-456"]


@respx.mock
def test_exchange_code_accepts_valid_verified_email_token():
    settings = OidcSettings(
        issuer="https://idp.example.com/realms/acme",
        client_id="fleetent-web",
        redirect_uri="https://fleetent.example.com/admin/oidc/callback",
    )
    private_key_pem = _private_key_pem()
    respx.get("https://idp.example.com/realms/acme/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": settings.issuer,
                "authorization_endpoint": "https://idp.example.com/oauth2/authorize",
                "token_endpoint": "https://idp.example.com/oauth2/token",
                "jwks_uri": "https://idp.example.com/oauth2/jwks",
            },
        )
    )
    respx.post("https://idp.example.com/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"id_token": _id_token(private_key_pem), "access_token": "at-123"},
        )
    )
    respx.get("https://idp.example.com/oauth2/jwks").mock(
        return_value=httpx.Response(200, json=_jwks(private_key_pem))
    )

    client = OidcRelyingParty(settings)

    identity = client.exchange_code(
        code="good-code",
        state="state-123",
        expected_state="state-123",
        nonce="nonce-123",
        expected_nonce="nonce-123",
    )

    assert identity.email == "person@example.com"
    assert identity.claims["email_verified"] is True


@pytest.mark.parametrize(
    ("token_kwargs", "state", "expected_state", "nonce", "expected_nonce", "message"),
    [
        ({}, "wrong-state", "state-123", "nonce-123", "nonce-123", "state"),
        ({}, "state-123", "state-123", "wrong-nonce", "nonce-123", "nonce"),
        ({"email_verified": False}, "state-123", "state-123", "nonce-123", "nonce-123", "email"),
        ({"email": None}, "state-123", "state-123", "nonce-123", "nonce-123", "email"),
        ({"issuer": "https://evil.example.com"}, "state-123", "state-123", "nonce-123", "nonce-123", "issuer"),
        ({"audience": "other-client"}, "state-123", "state-123", "nonce-123", "nonce-123", "aud"),
        ({"expires_at": 1}, "state-123", "state-123", "nonce-123", "nonce-123", "expired"),
    ],
)
@respx.mock
def test_exchange_code_rejects_invalid_state_nonce_or_id_token_claims(
    token_kwargs,
    state,
    expected_state,
    nonce,
    expected_nonce,
    message,
):
    settings = OidcSettings(
        issuer="https://idp.example.com/realms/acme",
        client_id="fleetent-web",
        redirect_uri="https://fleetent.example.com/admin/oidc/callback",
    )
    private_key_pem = _private_key_pem()
    respx.get("https://idp.example.com/realms/acme/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": settings.issuer,
                "authorization_endpoint": "https://idp.example.com/oauth2/authorize",
                "token_endpoint": "https://idp.example.com/oauth2/token",
                "jwks_uri": "https://idp.example.com/oauth2/jwks",
            },
        )
    )
    respx.post("https://idp.example.com/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"id_token": _id_token(private_key_pem, **token_kwargs), "access_token": "at-123"},
        )
    )
    respx.get("https://idp.example.com/oauth2/jwks").mock(
        return_value=httpx.Response(200, json=_jwks(private_key_pem))
    )

    client = OidcRelyingParty(settings)

    with pytest.raises(OidcAuthError, match=message):
        client.exchange_code(
            code="bad-code",
            state=state,
            expected_state=expected_state,
            nonce=nonce,
            expected_nonce=expected_nonce,
        )


@respx.mock
def test_exchange_code_rejects_bad_signature():
    settings = OidcSettings(
        issuer="https://idp.example.com/realms/acme",
        client_id="fleetent-web",
        redirect_uri="https://fleetent.example.com/admin/oidc/callback",
    )
    signing_key = _private_key_pem()
    jwks_key = _private_key_pem()
    respx.get("https://idp.example.com/realms/acme/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": settings.issuer,
                "authorization_endpoint": "https://idp.example.com/oauth2/authorize",
                "token_endpoint": "https://idp.example.com/oauth2/token",
                "jwks_uri": "https://idp.example.com/oauth2/jwks",
            },
        )
    )
    respx.post("https://idp.example.com/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"id_token": _id_token(signing_key), "access_token": "at-123"},
        )
    )
    respx.get("https://idp.example.com/oauth2/jwks").mock(
        return_value=httpx.Response(200, json=_jwks(jwks_key))
    )

    client = OidcRelyingParty(settings)

    with pytest.raises(OidcAuthError, match="signature"):
        client.exchange_code(
            code="bad-signature",
            state="state-123",
            expected_state="state-123",
            nonce="nonce-123",
            expected_nonce="nonce-123",
        )
