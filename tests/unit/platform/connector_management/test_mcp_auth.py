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
