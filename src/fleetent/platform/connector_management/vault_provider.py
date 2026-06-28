"""Vault-backed connector credential provider."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from fleetent import agent_store, connectors, user_store
from fleetent.platform.connector_management import (
    agent_service_grant_store,
    external_credential_store,
    external_service_store,
    service_providers,
)

_logger = logging.getLogger(__name__)


def _consent_url(user_id: str, service_id: str) -> str:
    return f"/admin/connectors/authorize/{service_id}?user_id={user_id}"


def _resolve_principal(user_id: str, service_id: str, agent_name: str | None) -> str:
    """Return the effective user_id for credential lookup based on the agent's run_as grant.

    When agent_name is provided, we check the agent's grant for this service:
    - run_as=agent: use the agent's service-principal (``agent:<id>``).
    - run_as=user or no grant: use the original caller's user_id.
    Falls back silently to user_id if the agent name can't be resolved.
    """
    if agent_name is None:
        return user_id
    agent = agent_store.get_by_name(agent_name)
    if agent is None:
        return user_id
    for grant in agent_service_grant_store.list_services_for_agent(agent.id):
        if grant["service_id"] == service_id:
            if grant.get("run_as") == "agent":
                return user_store.get_or_create_service_principal(agent.id)
            break
    return user_id


def _submit_url(service_id: str) -> str:
    """Where a user submits their own API key (no OAuth jump for apikey services)."""
    return f"/admin/connectors/{service_id}/credentials"


def _service_enabled(service: dict[str, object] | None) -> bool:
    return service is None or service.get("enabled") is not False


def _disabled_service_result(
    user_id: str,
    service_id: str,
    protocol: str | None,
) -> connectors.NeedsConsent:
    if protocol == "apikey":
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_submit_url(service_id),
        )
    return connectors.NeedsConsent(
        connector=service_id,
        consent_url=_consent_url(user_id, service_id),
    )


def _get_apikey_credential(
    user_id: str, service_id: str
) -> connectors.Credential | connectors.NeedsConsent:
    """Resolve an ``apikey``-protocol credential.

    API keys carry no refresh concept, so this path never touches the OAuth refresh
    logic or the token expiry check: a stored authorized key resolves to a
    ``Credential``; anything else asks the user to submit their key.
    """
    credential = external_credential_store.get_credential(user_id, service_id)
    if credential is None or credential["status"] != "authorized":
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_submit_url(service_id),
        )
    return connectors.Credential(connector=service_id, client=dict(credential["payload"]))


def _expires_at(payload: dict[str, object]) -> datetime | None:
    raw = payload.get("expires_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_expired(payload: dict[str, object]) -> bool:
    expires_at = _expires_at(payload)
    return expires_at is not None and expires_at <= datetime.now(UTC)


def _refresh_tokens(
    user_id: str, service_id: str, credential: dict[str, object], scopes: list[str]
) -> connectors.Credential | connectors.NeedsConsent | connectors.CredentialError:
    payload = dict(credential["payload"])
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_consent_url(user_id, service_id),
        )

    service = external_service_store.get_service(service_id)
    protocol = service.get("protocol") if service is not None else None
    if not _service_enabled(service):
        return _disabled_service_result(
            user_id, service_id, protocol if isinstance(protocol, str) else None
        )
    oauth_config = service.get("oauth_config", {}) if service is not None else {}
    token_url = oauth_config.get("token")
    client_id = oauth_config.get("client_id")
    if not isinstance(token_url, str) or not token_url:
        return connectors.CredentialError(
            connector=service_id,
            message="missing token endpoint configuration",
            retryable=False,
        )

    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    if isinstance(client_id, str) and client_id:
        data["client_id"] = client_id
    if scopes:
        data["scope"] = " ".join(scopes)
    client_secret = service_providers.client_secret_for(service_id)
    if client_secret:
        data["client_secret"] = client_secret

    try:
        response = httpx.post(token_url, data=data, timeout=10.0)
    except httpx.HTTPError as exc:
        external_credential_store.put_oauth_credential(
            user_id,
            service_id,
            payload,
            updated_by=user_id,
            status="error",
        )
        _logger.warning(
            "connector refresh failed connector=%s user_id=%s error=%s",
            service_id,
            user_id,
            exc.__class__.__name__,
        )
        return connectors.CredentialError(
            connector=service_id,
            message="credential refresh failed",
            retryable=True,
        )

    if response.status_code == 400 and response.headers.get("content-type", "").startswith(
        "application/json"
    ):
        error = response.json().get("error")
        if error == "invalid_grant":
            external_credential_store.put_oauth_credential(
                user_id,
                service_id,
                payload,
                updated_by=user_id,
                status="needs_reauth",
            )
            return connectors.NeedsConsent(
                connector=service_id,
                consent_url=_consent_url(user_id, service_id),
            )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        external_credential_store.put_oauth_credential(
            user_id,
            service_id,
            payload,
            updated_by=user_id,
            status="error",
        )
        _logger.warning(
            "connector refresh http failure connector=%s user_id=%s status_code=%s error=%s",
            service_id,
            user_id,
            response.status_code,
            exc.__class__.__name__,
        )
        return connectors.CredentialError(
            connector=service_id,
            message="credential refresh failed",
            retryable=True,
        )

    refreshed = response.json()
    merged = dict(payload)
    merged.update(refreshed)
    if "refresh_token" not in refreshed:
        merged["refresh_token"] = refresh_token
    if scopes and "scopes" not in merged:
        merged["scopes"] = scopes
    external_credential_store.put_oauth_credential(
        user_id,
        service_id,
        merged,
        updated_by=user_id,
        status="authorized",
    )
    stored = external_credential_store.get_credential(user_id, service_id)
    assert stored is not None
    client = dict(stored["payload"])
    if scopes:
        client.setdefault("scopes", scopes)
    return connectors.Credential(connector=service_id, client=client)


def revoke_credential(user_id: str, service_id: str) -> dict[str, bool]:
    credential = external_credential_store.get_credential(user_id, service_id)
    if credential is None:
        return {"revoked": True}

    payload = dict(credential["payload"])
    external_credential_store.delete_credential(user_id, service_id)

    service = external_service_store.get_service(service_id)
    oauth_config = service.get("oauth_config", {}) if service is not None else {}
    revoke_url = oauth_config.get("revoke")
    token = payload.get("refresh_token") or payload.get("access_token")
    if not isinstance(revoke_url, str) or not revoke_url or not isinstance(token, str) or not token:
        return {"revoked": True}

    data = {"token": token}
    client_id = oauth_config.get("client_id")
    if isinstance(client_id, str) and client_id:
        data["client_id"] = client_id

    try:
        response = httpx.post(revoke_url, data=data, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.warning(
            "connector revoke failed connector=%s user_id=%s error=%s",
            service_id,
            user_id,
            exc.__class__.__name__,
        )
    return {"revoked": True}


def get_credential(
    user_id: str,
    service_id: str,
    scopes: list[str],
    agent_name: str | None = None,
) -> connectors.Credential | connectors.NeedsConsent | connectors.CredentialError:
    principal_user_id = _resolve_principal(user_id, service_id, agent_name)
    service = external_service_store.get_service(service_id)
    protocol = service.get("protocol") if service is not None else None
    if not _service_enabled(service):
        return _disabled_service_result(
            principal_user_id,
            service_id,
            protocol if isinstance(protocol, str) else None,
        )
    if protocol == "apikey":
        return _get_apikey_credential(principal_user_id, service_id)

    credential = external_credential_store.get_credential(principal_user_id, service_id)
    if credential is None:
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_consent_url(principal_user_id, service_id),
        )
    if credential["status"] == "needs_reauth":
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_consent_url(principal_user_id, service_id),
        )
    payload = dict(credential["payload"])
    if _is_expired(payload):
        return _refresh_tokens(principal_user_id, service_id, credential, scopes)
    if credential["status"] == "error":
        return connectors.CredentialError(
            connector=service_id,
            message="credential refresh failed",
            retryable=True,
        )
    if credential["status"] != "authorized":
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_consent_url(principal_user_id, service_id),
        )
    if scopes:
        payload.setdefault("scopes", scopes)
    return connectors.Credential(connector=service_id, client=payload)
