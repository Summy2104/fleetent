"""Standalone self-hosted per-user api-key credential form + submit handler (Group 3, D4).

In a standalone deployment (no platform) the agent self-hosts the credential-submission
endpoint, closing the secure-form loop entirely on the agent side. Sibling to
:mod:`standalone_callback` (OAuth), but far simpler — there is no ``code`` exchange:

* :func:`render_credential_form` returns a minimal HTML form (one masked input + the
  one-shot ``state`` as a hidden field). The state is the only CSRF token; the key is never
  echoed back.
* :func:`handle_credential_submit` consumes the one-shot ``state`` from the shared state
  store to reverse-resolve ``(user_id, agent_id, server_id)`` — identity comes *only* from
  ``state``, never from the request's login state (the end user has no fleetent account) —
  then persists the submitted key, encrypted, under that triple as ``credential_kind=
  "static"``. An unknown / expired / already-consumed ``state`` (or a missing key) is
  rejected with no write.

This module imports only sibling MCP modules; it never imports the platform package (agent
runtime stays decoupled) and holds no live resource at module scope (the store handle is
passed in).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fleetent.integrations.mcp import authorization as _authz
from fleetent.integrations.mcp.client import find_registered_server
from fleetent.integrations.mcp.credential_submission import render_credential_form
from fleetent.integrations.mcp.per_user_tokens import UserToken, UserTokenStore

logger = logging.getLogger(__name__)

# Re-exported for callers that wired against this module before render moved to the neutral
# ``credential_submission`` (shared by standalone + managed). Kept importable here.
__all__ = ["CredentialResult", "handle_credential_submit", "render_credential_form"]


@dataclass(frozen=True)
class CredentialResult:
    """Outcome of handling a credential-form submission.

    Attributes:
        ok: True iff the key was stored.
        status: A short machine-readable status (``stored`` / ``invalid_input`` /
            ``invalid_state`` / ``unknown_server``).
        detail: A human-readable, log/page-safe description (never carries the key).
    """

    ok: bool
    status: str
    detail: str


def handle_credential_submit(
    *, state: str | None, key: str | None, store: UserTokenStore
) -> CredentialResult:
    """Complete a standalone credential-form submission (Group 3, 3.4).

    Identity is reverse-resolved from ``state`` alone (consumed one-shot from the shared
    state store): an unknown / expired / already-consumed ``state`` is rejected without any
    write. A missing key is rejected *before* consuming the state, so the user can retry the
    same link. On success the server is resolved by id and the key is stored, encrypted,
    under the ``(user, agent, server)`` triple from the state as ``credential_kind=static``.
    The request's own login state is never consulted.

    Args:
        state: The ``state`` form/query field.
        key: The submitted api-key/bearer secret.
        store: The local per-user token store to persist the key into (encrypts at rest).

    Returns:
        A :class:`CredentialResult` describing the outcome (never raises; the endpoint maps
        an ``ok=False`` result to a 4xx).
    """
    if not state or not key:
        # Don't consume the state on an incomplete submit — let the user retry the link.
        return CredentialResult(ok=False, status="invalid_input", detail="missing state or key")
    auth_state = _authz.get_oauth_state_store().consume(state)
    if auth_state is None:
        logger.info("mcp_credential_submit_rejected reason=invalid_state")
        return CredentialResult(
            ok=False, status="invalid_state", detail="invalid, expired, or already-used state"
        )
    server = find_registered_server(auth_state.server_id)
    if server is None:
        logger.warning("mcp_credential_submit_unknown_server server_id=%s", auth_state.server_id)
        return CredentialResult(
            ok=False, status="unknown_server", detail="unknown server for this submission"
        )
    store.put(
        auth_state.user_id,
        auth_state.agent_id,
        server.id,
        UserToken(access_token=key, refresh_token=None, expires_at=None, scope=None),
        credential_kind="static",
    )
    logger.info(
        "mcp_credential_submit_stored server_id=%s user_id=%s agent_id=%s",
        server.id,
        auth_state.user_id,
        auth_state.agent_id,
    )
    return CredentialResult(ok=True, status="stored", detail="credential saved")
