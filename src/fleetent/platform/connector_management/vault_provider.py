"""Vault-backed connector credential provider."""

from __future__ import annotations

from fleetent import connectors
from fleetent.platform.connector_management import external_credential_store


def _consent_url(user_id: str, service_id: str) -> str:
    return f"/admin/connectors/authorize/{service_id}?user_id={user_id}"


def get_credential(
    user_id: str, service_id: str, scopes: list[str]
) -> connectors.Credential | connectors.NeedsConsent:
    credential = external_credential_store.get_credential(user_id, service_id)
    if credential is None or credential["status"] != "authorized":
        return connectors.NeedsConsent(
            connector=service_id,
            consent_url=_consent_url(user_id, service_id),
        )
    payload = dict(credential["payload"])
    if scopes:
        payload.setdefault("scopes", scopes)
    return connectors.Credential(connector=service_id, client=payload)
