from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleetent.platform.connector_management.mcp_auth import (
    ApiKeyMcpAuthConfig,
    OAuthClientCredentialsMcpAuthConfig,
    parse_mcp_auth_config,
)


def test_parse_mcp_auth_config_uses_auth_type_discriminator_for_api_key() -> None:
    auth = parse_mcp_auth_config("api_key", {"key_env": "FLEETENT_MCP_API_KEY"})

    assert isinstance(auth, ApiKeyMcpAuthConfig)
    assert auth.auth_type == "api_key"
    assert auth.key_env == "FLEETENT_MCP_API_KEY"


def test_parse_mcp_auth_config_reuses_oauth_settings_fields_for_client_credentials() -> None:
    auth = parse_mcp_auth_config(
        "oauth_client_credentials",
        {
            "token_url": "https://auth.internal/token",
            "client_id": "mcp-client",
            "client_secret_env": "FLEETENT_MCP_CLIENT_SECRET",
            "scope": "tools:read tools:write",
        },
    )

    assert isinstance(auth, OAuthClientCredentialsMcpAuthConfig)
    assert auth.auth_type == "oauth_client_credentials"
    assert auth.grant == "client_credentials"
    assert auth.token_url == "https://auth.internal/token"
    assert auth.client_id == "mcp-client"
    assert auth.client_secret_env == "FLEETENT_MCP_CLIENT_SECRET"
    assert auth.scope == "tools:read tools:write"


@pytest.mark.parametrize(
    ("auth_type", "auth_config", "message"),
    [
        ("api_key", {}, "key_env"),
        ("oauth_client_credentials", {"token_url": "https://auth.internal/token"}, "client_id"),
        ("bogus", {}, "auth_type"),
    ],
)
def test_parse_mcp_auth_config_rejects_missing_or_unknown_values(
    auth_type: str, auth_config: object, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_mcp_auth_config(auth_type, auth_config)


def test_parse_mcp_auth_config_supports_authorization_code() -> None:
    # Slice 2: the discriminated union gains a per-user authorization_code variant. PKCE
    # public clients may omit client_secret_env, so it is NOT required (unlike client_credentials).
    from fleetent.mcp_auth_models import OAuthAuthorizationCodeMcpAuthConfig

    auth = parse_mcp_auth_config(
        "oauth_authorization_code",
        {
            "authorization_endpoint": "https://auth.internal/authorize",
            "token_url": "https://auth.internal/token",
            "client_id": "fleetent-crm",
            "scope": "mcp.read",
            "redirect_path": "/oauth/callback",
            "client_secret_env": "CRM_OAUTH_SECRET",
        },
    )

    assert isinstance(auth, OAuthAuthorizationCodeMcpAuthConfig)
    assert auth.auth_type == "oauth_authorization_code"
    assert auth.grant == "authorization_code"
    assert auth.authorization_endpoint == "https://auth.internal/authorize"
    assert auth.redirect_path == "/oauth/callback"
    assert auth.client_id == "fleetent-crm"
    assert "client_secret_env" in OAuthAuthorizationCodeMcpAuthConfig.secret_env_fields


def test_authorization_code_requires_core_fields() -> None:
    with pytest.raises(ValidationError, match="authorization_endpoint|client_id|token_url"):
        parse_mcp_auth_config("oauth_authorization_code", {"client_id": "x"})


def test_auth_config_models_live_in_neutral_module_importable_by_both_planes() -> None:
    # The schema is the single source for validation/materialize/frontend; it MUST be
    # importable without crossing into platform internals so the agent runtime (banned from
    # importing platform.*) can consume it. The platform path is a re-export shim.
    import fleetent.mcp_auth_models as neutral
    from fleetent.platform.connector_management import mcp_auth as shim

    for name in (
        "NoMcpAuthConfig",
        "ApiKeyMcpAuthConfig",
        "OAuthClientCredentialsMcpAuthConfig",
        "OAuthAuthorizationCodeMcpAuthConfig",
        "McpAuthConfig",
        "parse_mcp_auth_config",
    ):
        assert hasattr(neutral, name), f"neutral module missing {name}"
        assert getattr(shim, name) is getattr(neutral, name), f"shim {name} not re-export"
