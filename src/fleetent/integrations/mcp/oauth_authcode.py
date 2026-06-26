"""Transport-/deployment-agnostic OAuth 2.1 Authorization Code protocol logic (D6).

Pure protocol logic shared by standalone and (future) managed per-user OAuth: PKCE
(S256) generation/verification, authorization-URL assembly, a one-shot TTL-bounded
state store, and code-exchange / refresh request construction + response parsing +
auth-error classification.

This module deliberately knows nothing about MCP sessions, subprocesses, the agent
runtime, or the platform. HTTP is performed through a caller-supplied
``httpx.AsyncClient`` (so token exchange/refresh is unit-testable over MockTransport
without touching the network), the clock is injectable (so TTL/expiry are testable),
and the state store is an instance — never a module-level mutable global — so it can be
swapped in tests and never leaks live resources at import time.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

# RFC 7636 §4.1: a 32-byte verifier base64url-encodes to 43 chars, well within 43..128.
_VERIFIER_BYTES = 32
# Random state must be unguessable; 32 bytes base64url ≈ 43 chars of entropy.
_STATE_BYTES = 32
_DEFAULT_STATE_TTL_SECONDS = 600.0


# ── errors ─────────────────────────────────────────────────────────────────────


class OAuthAuthError(RuntimeError):
    """A genuine credential/authorization failure at the token endpoint.

    Raised on 401 / ``invalid_client`` / ``invalid_grant`` / ``unauthorized_client``:
    retrying with the same credentials is futile, so callers surface re-authorization
    guidance rather than retry.
    """


class OAuthTransientError(RuntimeError):
    """A transient token-endpoint failure (5xx / network / non-credential 4xx).

    Distinct from :class:`OAuthAuthError`: the request may succeed on retry, so callers
    may back off and try again rather than forcing re-authorization.
    """


# ── PKCE (RFC 7636, S256) ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class PkcePair:
    """A PKCE verifier/challenge pair.

    Attributes:
        verifier: The high-entropy ``code_verifier`` kept server-side until code exchange.
        challenge: The ``code_challenge`` (S256 of the verifier) sent in the auth request.
        method: The challenge method; always ``"S256"`` for this module.
    """

    verifier: str
    challenge: str
    method: str = "S256"


def _b64url_nopad(data: bytes) -> str:
    """base64url-encode without padding (RFC 7636 challenge/verifier encoding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _challenge_for(verifier: str) -> str:
    """Compute the S256 ``code_challenge`` for a given ``code_verifier``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url_nopad(digest)


def generate_pkce() -> PkcePair:
    """Generate a fresh PKCE verifier/challenge pair using the S256 method.

    Returns:
        A :class:`PkcePair` whose ``challenge`` is the S256 hash of a cryptographically
        random ``verifier``.
    """
    verifier = _b64url_nopad(secrets.token_bytes(_VERIFIER_BYTES))
    return PkcePair(verifier=verifier, challenge=_challenge_for(verifier), method="S256")


def verify_pkce(verifier: str, challenge: str) -> bool:
    """Whether ``challenge`` is the S256 challenge of ``verifier``.

    Uses a constant-time comparison so a mismatch does not leak via timing.

    Args:
        verifier: The ``code_verifier`` to test.
        challenge: The ``code_challenge`` to compare against.

    Returns:
        True iff ``challenge == S256(verifier)``.
    """
    return secrets.compare_digest(_challenge_for(verifier), challenge)


# ── authorization URL assembly ──────────────────────────────────────────────────


def build_authorization_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
) -> str:
    """Assemble an OAuth 2.1 Authorization Code request URL (with PKCE S256).

    Existing query parameters on ``authorization_endpoint`` (e.g. an ``audience``) are
    preserved; the OAuth parameters are appended. An empty ``scope`` is omitted entirely.

    Args:
        authorization_endpoint: The authorization server's ``/authorize`` URL (may carry
            its own query parameters).
        client_id: The registered OAuth client id.
        redirect_uri: The callback URI; MUST exactly match the AS-registered value.
        scope: Space-delimited scopes, or "" to omit the ``scope`` parameter.
        state: An unguessable, one-shot state token bound to (user, agent, server).
        code_challenge: The PKCE S256 ``code_challenge``.

    Returns:
        The fully-assembled authorization URL.
    """
    parsed = urlparse(authorization_endpoint)
    # parse_qs yields list-valued dict; flatten to preserve existing single values + order.
    query: list[tuple[str, str]] = [(k, v) for k, vs in parse_qs(parsed.query).items() for v in vs]
    query.append(("response_type", "code"))
    query.append(("client_id", client_id))
    query.append(("redirect_uri", redirect_uri))
    if scope:
        query.append(("scope", scope))
    query.append(("state", state))
    query.append(("code_challenge", code_challenge))
    query.append(("code_challenge_method", "S256"))
    return urlunparse(parsed._replace(query=urlencode(query)))


# ── state management (one-shot, TTL, injectable store + clock) ───────────────────


@dataclass(frozen=True)
class AuthState:
    """The (user, agent, server) binding plus PKCE verifier carried by a ``state`` token."""

    user_id: str
    agent_id: str
    server_id: str
    verifier: str


@dataclass
class _StateEntry:
    state: AuthState
    expires_at: float


class StateStore(Protocol):
    """Injectable one-shot store binding a ``state`` token to its :class:`AuthState`.

    Implementations MUST issue unguessable states, bind each to a (user, agent, server)
    plus PKCE verifier, enforce a short TTL, and allow each state to be consumed at most
    once. They MUST NOT be held as module-level mutable globals.
    """

    def issue(self, user_id: str, agent_id: str, server_id: str, verifier: str) -> str:
        """Mint and store a new state token bound to the given tuple + verifier."""
        ...

    def consume(self, state: str) -> AuthState | None:
        """Atomically validate + invalidate ``state``, returning its binding or None.

        Returns None when the state is unknown, already consumed, or expired.
        """
        ...


class InMemoryStateStore:
    """Default in-process :class:`StateStore` (standalone). Not a module-level global.

    The clock is injectable so TTL expiry is unit-testable without sleeping.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = _DEFAULT_STATE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an empty store.

        Args:
            ttl_seconds: How long an issued state remains valid before expiry.
            clock: Monotonic-ish time source (seconds); injectable for tests.
        """
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _StateEntry] = {}

    def issue(self, user_id: str, agent_id: str, server_id: str, verifier: str) -> str:
        state = secrets.token_urlsafe(_STATE_BYTES)
        self._entries[state] = _StateEntry(
            state=AuthState(
                user_id=user_id, agent_id=agent_id, server_id=server_id, verifier=verifier
            ),
            expires_at=self._clock() + self._ttl,
        )
        return state

    def consume(self, state: str) -> AuthState | None:
        # Pop first so a valid-but-expired state is also evicted (one-shot semantics).
        entry = self._entries.pop(state, None)
        if entry is None:
            return None
        if self._clock() > entry.expires_at:
            return None
        return entry.state


# ── token results + code exchange / refresh ─────────────────────────────────────


@dataclass(frozen=True)
class TokenResult:
    """Parsed token-endpoint response.

    Attributes:
        access_token: The bearer access token.
        refresh_token: The refresh token, if the AS returned one (else None).
        expires_at: Absolute expiry (same clock as the injected ``now``), or None when
            the AS omitted ``expires_in``.
        scope: The granted scope string, if returned (else None).
        token_type: The token type (typically ``Bearer``).
    """

    access_token: str
    refresh_token: str | None
    expires_at: float | None
    scope: str | None
    token_type: str


def is_auth_error_response(resp: httpx.Response) -> bool:
    """Whether a token-endpoint response is a genuine credential/auth error.

    Mirrors the client_credentials classifier in ``client.py``: 401, or a 400/403 whose
    JSON ``error`` is ``invalid_client`` / ``invalid_grant`` / ``unauthorized_client``.
    All other statuses (5xx, non-credential 4xx) are transient/retryable.

    Args:
        resp: The token-endpoint HTTP response.

    Returns:
        True for genuine auth errors, False for transient/other failures.
    """
    if resp.status_code == 401:
        return True
    if resp.status_code in (400, 403):
        try:
            err = resp.json().get("error")
        except Exception:  # noqa: BLE001 — non-JSON 4xx is not a credential error
            err = None
        return err in ("invalid_client", "invalid_grant", "unauthorized_client")
    return False


def _parse_token_response(
    resp: httpx.Response,
    *,
    now: Callable[[], float],
    fallback_refresh_token: str | None,
) -> TokenResult:
    """Parse a successful token response into a :class:`TokenResult`.

    Classifies non-2xx responses first (raising auth vs transient), then parses the JSON.

    Args:
        resp: The token-endpoint response.
        now: Time source used to compute absolute ``expires_at`` from ``expires_in``.
        fallback_refresh_token: Refresh token to keep when the AS does not rotate one
            (i.e. omits ``refresh_token``); None for the initial code exchange.
    """
    if resp.status_code >= 400:
        if is_auth_error_response(resp):
            raise OAuthAuthError(
                f"token endpoint rejected the request (status={resp.status_code}): "
                "re-authorization required"
            )
        raise OAuthTransientError(f"token endpoint transient failure (status={resp.status_code})")
    try:
        data: dict[str, Any] = resp.json()
    except Exception as exc:  # noqa: BLE001 — malformed success body is transient
        raise OAuthTransientError("token endpoint returned a non-JSON success body") from exc

    expires_in = data.get("expires_in")
    expires_at = now() + float(expires_in) if expires_in is not None else None
    return TokenResult(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token") or fallback_refresh_token,
        expires_at=expires_at,
        scope=data.get("scope"),
        token_type=data.get("token_type", "Bearer"),
    )


async def _post_token(
    *,
    token_url: str,
    form: dict[str, str],
    http_client: httpx.AsyncClient,
    now: Callable[[], float],
    fallback_refresh_token: str | None,
) -> TokenResult:
    """POST a form-encoded grant to the token endpoint and parse the result.

    Network/transport failures are reclassified as :class:`OAuthTransientError` so callers
    treat them as retryable rather than crashing.
    """
    try:
        resp = await http_client.post(token_url, data=form)
    except httpx.HTTPError as exc:
        raise OAuthTransientError(f"token endpoint request failed: {exc}") from exc
    return _parse_token_response(resp, now=now, fallback_refresh_token=fallback_refresh_token)


async def exchange_code(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    http_client: httpx.AsyncClient,
    now: Callable[[], float] = time.time,
) -> TokenResult:
    """Exchange an authorization ``code`` for tokens (grant_type=authorization_code).

    Uses ``client_secret_post`` client authentication (secret in the form body) and
    includes the PKCE ``code_verifier`` and the exact ``redirect_uri`` per RFC 6749 §4.1.3.

    Args:
        token_url: The authorization server's token endpoint.
        client_id: The registered OAuth client id.
        client_secret: The client secret (sent via client_secret_post).
        code: The authorization code returned to the callback.
        code_verifier: The PKCE verifier matching the earlier ``code_challenge``.
        redirect_uri: The redirect URI used in the authorization request (must match).
        http_client: Caller-supplied async HTTP client (injectable/mockable).
        now: Time source for computing ``expires_at``; defaults to ``time.time``.

    Returns:
        The parsed :class:`TokenResult`.

    Raises:
        OAuthAuthError: On a genuine credential/grant rejection.
        OAuthTransientError: On a transient (5xx/network/non-credential) failure.
    """
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return await _post_token(
        token_url=token_url,
        form=form,
        http_client=http_client,
        now=now,
        fallback_refresh_token=None,
    )


async def refresh_token(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    http_client: httpx.AsyncClient,
    now: Callable[[], float] = time.time,
) -> TokenResult:
    """Refresh an access token (grant_type=refresh_token).

    Uses ``client_secret_post`` client authentication. When the AS does not rotate the
    refresh token (omits ``refresh_token`` in the response), the returned result keeps the
    caller's existing ``refresh_token`` so it remains usable.

    Args:
        token_url: The authorization server's token endpoint.
        client_id: The registered OAuth client id.
        client_secret: The client secret (sent via client_secret_post).
        refresh_token: The current refresh token.
        http_client: Caller-supplied async HTTP client (injectable/mockable).
        now: Time source for computing ``expires_at``; defaults to ``time.time``.

    Returns:
        The parsed :class:`TokenResult`.

    Raises:
        OAuthAuthError: On a genuine credential/grant rejection (e.g. revoked refresh).
        OAuthTransientError: On a transient (5xx/network/non-credential) failure.
    """
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return await _post_token(
        token_url=token_url,
        form=form,
        http_client=http_client,
        now=now,
        fallback_refresh_token=refresh_token,
    )
