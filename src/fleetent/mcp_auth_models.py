"""Neutral, plane-agnostic schema for MCP server static auth (`auth_type` + `auth_config`).

This module is the single source of truth for MCP auth configuration shape, shared by
both planes: the platform control plane (registry validation, materialize translation,
admin API / frontend form) and the agent runtime (`integrations/mcp`). It lives at the
top level — not under `platform/` — so the agent runtime can import it without violating
the agent⊥platform rule (agent MUST NOT import `fleetent.platform.*`). The historical
import path `fleetent.platform.connector_management.mcp_auth` is kept as a re-export shim.

The auth types form a pydantic discriminated union keyed on `auth_type`; a new auth type
is added by declaring one model here (and a frontend form branch) without changing the
`mcp_servers` table. Each model marks which fields are secret env-var *references*
(`secret_env_fields`); secret *values* never live in the registry or `auth_config`.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from fleetent.config import McpOAuthSettings


class NoMcpAuthConfig(BaseModel):
    auth_type: Literal["none"] = "none"
    secret_env_fields: ClassVar[frozenset[str]] = frozenset()


class ApiKeyMcpAuthConfig(BaseModel):
    auth_type: Literal["api_key"] = "api_key"
    key_env: str
    secret_env_fields: ClassVar[frozenset[str]] = frozenset({"key_env"})


class OAuthClientCredentialsMcpAuthConfig(McpOAuthSettings):
    auth_type: Literal["oauth_client_credentials"] = "oauth_client_credentials"
    grant: Literal["client_credentials"] = "client_credentials"
    type: Literal["oauth2"] = "oauth2"
    secret_env_fields: ClassVar[frozenset[str]] = frozenset({"client_secret_env"})

    @model_validator(mode="after")
    def _require_client_credentials_fields(self) -> OAuthClientCredentialsMcpAuthConfig:
        missing = [
            name
            for name in ("token_url", "client_id", "client_secret_env")
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(
                "oauth_client_credentials auth requires non-empty " + ", ".join(missing)
            )
        return self


class OAuthAuthorizationCodeMcpAuthConfig(McpOAuthSettings):
    """Per-user OAuth 2.1 authorization_code grant (slice mcp-per-user-oauth2).

    Unlike client_credentials, `client_secret_env` is OPTIONAL: OAuth 2.1 public clients
    authenticate with PKCE and no client secret. Required core fields (authorization
    endpoint, token endpoint, client id) are enforced by ``McpOAuthSettings``'s
    authorization_code validator.
    """

    auth_type: Literal["oauth_authorization_code"] = "oauth_authorization_code"
    grant: Literal["authorization_code"] = "authorization_code"
    type: Literal["oauth2"] = "oauth2"
    secret_env_fields: ClassVar[frozenset[str]] = frozenset({"client_secret_env"})


McpAuthConfig = Annotated[
    NoMcpAuthConfig
    | ApiKeyMcpAuthConfig
    | OAuthClientCredentialsMcpAuthConfig
    | OAuthAuthorizationCodeMcpAuthConfig,
    Field(discriminator="auth_type"),
]

_AUTH_CONFIG_ADAPTER = TypeAdapter(McpAuthConfig)


def parse_mcp_auth_config(auth_type: str | None, auth_config: object) -> McpAuthConfig:
    payload = dict(auth_config) if isinstance(auth_config, dict) else {}
    payload["auth_type"] = "api_key" if auth_type == "bearer" else (auth_type or "none")
    return _AUTH_CONFIG_ADAPTER.validate_python(payload)
