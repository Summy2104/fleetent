import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from fleetent.oidc_config import OidcSettings

_CLOCK_SKEW_SECONDS = 30
_FLOW_COOKIE_TTL_SECONDS = 300


class OidcAuthError(RuntimeError):
    """Raised when the OIDC callback cannot be trusted."""


@dataclass(frozen=True)
class OidcProviderMetadata:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    issuer: str


@dataclass(frozen=True)
class OidcIdentity:
    email: str
    claims: dict[str, Any]


@dataclass(frozen=True)
class OidcFlowState:
    state: str
    nonce: str


class OidcRelyingParty:
    """Small provider-agnostic OIDC relying-party client."""

    def __init__(
        self,
        settings: OidcSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=10.0)

    def build_authorize_url(self, *, state: str, nonce: str) -> str:
        metadata = self._discover()
        query = urlencode(
            {
                "client_id": self._settings.client_id,
                "redirect_uri": self._settings.redirect_uri,
                "response_type": "code",
                "scope": " ".join(self._settings.scopes),
                "state": state,
                "nonce": nonce,
            }
        )
        return f"{metadata.authorization_endpoint}?{query}"

    def exchange_code(
        self,
        *,
        code: str,
        state: str,
        expected_state: str,
        nonce: str,
        expected_nonce: str,
    ) -> OidcIdentity:
        if state != expected_state:
            raise OidcAuthError("invalid state")
        if nonce != expected_nonce:
            raise OidcAuthError("invalid nonce")

        metadata = self._discover()
        token = self._exchange_token(metadata, code)
        claims = self._validate_id_token(
            metadata,
            token.get("id_token"),
            expected_nonce=expected_nonce,
        )
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise OidcAuthError("email claim missing")
        if claims.get("email_verified") is not True:
            raise OidcAuthError("email claim must be verified")
        return OidcIdentity(email=email, claims=claims)

    def _discover(self) -> OidcProviderMetadata:
        url = f"{self._settings.issuer.rstrip('/')}/.well-known/openid-configuration"
        response = self._http.get(url)
        response.raise_for_status()
        body = response.json()
        return OidcProviderMetadata(
            authorization_endpoint=str(body["authorization_endpoint"]),
            token_endpoint=str(body["token_endpoint"]),
            jwks_uri=str(body["jwks_uri"]),
            issuer=str(body.get("issuer", self._settings.issuer)),
        )

    def _exchange_token(self, metadata: OidcProviderMetadata, code: str) -> dict[str, Any]:
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.redirect_uri,
            "client_id": self._settings.client_id,
        }
        client_secret = self._client_secret()
        if client_secret:
            body["client_secret"] = client_secret
        response = self._http.post(metadata.token_endpoint, data=body)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise OidcAuthError("token response must be a JSON object")
        return payload

    def _validate_id_token(
        self,
        metadata: OidcProviderMetadata,
        token: object,
        *,
        expected_nonce: str,
    ) -> dict[str, Any]:
        if not isinstance(token, str) or not token:
            raise OidcAuthError("id_token missing")
        jwks = self._jwks(metadata)
        try:
            decoded = jwt.decode(token, jwks, algorithms=["RS256"])
        except Exception as exc:  # pragma: no cover - authlib exception taxonomy is broad
            raise OidcAuthError("invalid id_token signature") from exc
        try:
            JWTClaimsRegistry(
                leeway=_CLOCK_SKEW_SECONDS,
            ).validate(decoded.claims)
        except Exception as exc:  # pragma: no cover - authlib exception taxonomy is broad
            raise OidcAuthError("id_token expired or not yet valid") from exc

        payload = dict(decoded.claims)
        if metadata.issuer != self._settings.issuer:
            raise OidcAuthError("issuer mismatch")
        if payload.get("iss") != self._settings.issuer:
            raise OidcAuthError("issuer mismatch")
        if not _audience_matches(payload.get("aud"), self._settings.client_id):
            raise OidcAuthError("audience mismatch")
        if payload.get("nonce") != expected_nonce:
            raise OidcAuthError("nonce mismatch")
        return payload

    def _jwks(self, metadata: OidcProviderMetadata) -> KeySet:
        response = self._http.get(metadata.jwks_uri)
        response.raise_for_status()
        return KeySet.import_key_set(response.json())

    def _client_secret(self) -> str:
        env_name = self._settings.client_secret_env
        if not env_name:
            return ""
        return os.environ.get(env_name, "")


def email_domain_allowed(email: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    if not domain:
        return False
    return domain in {allowed_domain.lower() for allowed_domain in allowed_domains}


def _oidc_tenant_for(email: str, claims: dict[str, Any], settings: OidcSettings) -> str:
    """Resolve the tenant for an OIDC-authenticated identity.

    Current decision A is a single configured tenant. Keep this indirection so the
    future domain-mapping variant can change here without touching the login flow.
    """

    del email, claims
    return settings.tenant


def _audience_matches(claim_aud: object, client_id: str) -> bool:
    if isinstance(claim_aud, str):
        return claim_aud == client_id
    if isinstance(claim_aud, list):
        return client_id in claim_aud
    return False


def encode_flow_state(state: str, nonce: str) -> str:
    payload = json.dumps({"state": state, "nonce": nonce, "iat": int(time.time())})
    return _fernet().encrypt(payload.encode("utf-8")).decode("ascii")


def decode_flow_state(value: str) -> OidcFlowState:
    try:
        raw = _fernet().decrypt(value.encode("ascii"), ttl=_FLOW_COOKIE_TTL_SECONDS)
    except InvalidToken as exc:
        raise OidcAuthError("invalid oidc flow cookie") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise OidcAuthError("invalid oidc flow cookie") from exc
    state = payload.get("state")
    nonce = payload.get("nonce")
    if not isinstance(state, str) or not state or not isinstance(nonce, str) or not nonce:
        raise OidcAuthError("invalid oidc flow cookie")
    return OidcFlowState(state=state, nonce=nonce)


def flow_cookie_ttl_seconds() -> int:
    return _FLOW_COOKIE_TTL_SECONDS


def _fernet() -> Fernet:
    key = os.environ.get("FLEETENT_SECRET_KEY", "")
    if not key:
        raise OidcAuthError("FLEETENT_SECRET_KEY is required for OIDC flow cookies")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise OidcAuthError("FLEETENT_SECRET_KEY must be a valid Fernet key") from exc
