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
    def _require_client_credentials_fields(self) -> "OAuthClientCredentialsMcpAuthConfig":
        missing = [
            name for name in ("token_url", "client_id", "client_secret_env") if not getattr(self, name)
        ]
        if missing:
            raise ValueError(
                "oauth_client_credentials auth requires non-empty " + ", ".join(missing)
            )
        return self


McpAuthConfig = Annotated[
    NoMcpAuthConfig | ApiKeyMcpAuthConfig | OAuthClientCredentialsMcpAuthConfig,
    Field(discriminator="auth_type"),
]

_AUTH_CONFIG_ADAPTER = TypeAdapter(McpAuthConfig)


def parse_mcp_auth_config(auth_type: str | None, auth_config: object) -> McpAuthConfig:
    payload = dict(auth_config) if isinstance(auth_config, dict) else {}
    payload["auth_type"] = "api_key" if auth_type == "bearer" else (auth_type or "none")
    return _AUTH_CONFIG_ADAPTER.validate_python(payload)
