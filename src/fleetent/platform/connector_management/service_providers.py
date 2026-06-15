"""Per-service OAuth2 adapter interface and registry.

Each adapter encapsulates the per-service differences in:
  - Authorization URL construction (extra params like access_type=offline)
  - code→token exchange (including client_secret from env)
  - token payload → tool client dict mapping
  - scope normalization

The factory selects an adapter by service_id. The ``external_services`` table
has no ``kind`` column (re-baseline finding, P6); service_id serves as the
factory key. Registering a new service requires only:
  1. ``register_provider(service_id, MyProvider())``  — at startup / in a plugin
  2. One ``external_services`` row via the admin API
No changes to dispatch or consent core are needed.

client_secret is never stored — ``client_secret_for(service_id)`` reads it from
the env var ``{SERVICE_ID_UPPER}_CLIENT_SECRET`` at call time.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class ServiceProvider(Protocol):
    """Adapter interface for per-service OAuth2 differences."""

    def build_authorize_params(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        scopes: list[str],
    ) -> dict[str, str]: ...

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_url: str,
    ) -> dict[str, Any]: ...

    def build_client(
        self,
        payload: dict[str, Any],
        scopes: list[str],
    ) -> dict[str, Any]: ...

    def normalize_scopes(self, scopes: list[str]) -> list[str]: ...


def client_secret_for(service_id: str) -> str:
    """Read the client_secret from env. Convention: {SERVICE_ID_UPPER}_CLIENT_SECRET."""
    key = service_id.upper().replace("-", "_") + "_CLIENT_SECRET"
    return os.environ.get(key, "")


class _GenericOAuth2Provider:
    """Generic OAuth2 adapter: standard authorization_code flow, no extras."""

    def build_authorize_params(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        scopes: list[str],
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if scopes:
            params["scope"] = " ".join(scopes)
        return params

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_url: str,
    ) -> dict[str, Any]:
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
        if client_secret:
            data["client_secret"] = client_secret
        response = httpx.post(token_url, data=data, timeout=10.0)
        response.raise_for_status()
        return dict(response.json())

    def build_client(
        self,
        payload: dict[str, Any],
        scopes: list[str],
    ) -> dict[str, Any]:
        client = dict(payload)
        if scopes:
            client.setdefault("scopes", scopes)
        return client

    def normalize_scopes(self, scopes: list[str]) -> list[str]:
        return scopes


class _GoogleDriveProvider(_GenericOAuth2Provider):
    """Google Drive OAuth2 adapter.

    Adds ``access_type=offline`` and ``prompt=consent`` to the authorization
    redirect so that Google issues a refresh token on first consent.
    """

    def build_authorize_params(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        scopes: list[str],
    ) -> dict[str, str]:
        params = super().build_authorize_params(client_id, redirect_uri, state, scopes)
        params["access_type"] = "offline"
        params["prompt"] = "consent"
        return params


class _GitHubProvider(_GenericOAuth2Provider):
    """GitHub OAuth2 adapter.

    GitHub uses a standard authorization_code flow with no offline/prompt extras.
    Access tokens are long-lived; refresh tokens are not issued by default.
    """


_REGISTRY: dict[str, ServiceProvider] = {
    "google-drive": _GoogleDriveProvider(),
    "github": _GitHubProvider(),
}

_GENERIC: ServiceProvider = _GenericOAuth2Provider()


def get_provider(service_id: str) -> ServiceProvider:
    """Return the adapter for service_id, falling back to the generic OAuth2 adapter."""
    return _REGISTRY.get(service_id, _GENERIC)


def register_provider(service_id: str, provider: ServiceProvider) -> None:
    """Register a custom adapter for a service_id (at startup, plugin, or test)."""
    _REGISTRY[service_id] = provider
