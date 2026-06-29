"""Re-export shim — MCP auth config schema moved to the neutral ``fleetent.mcp_auth_models``.

The schema now lives at the top level so the agent runtime can import it without crossing
into ``platform.*`` (agent⊥platform rule). This module preserves the historical import
path ``fleetent.platform.connector_management.mcp_auth`` for existing platform consumers.
"""

from __future__ import annotations

from fleetent.mcp_auth_models import (
    ApiKeyMcpAuthConfig,
    ApiKeyPerUserMcpAuthConfig,
    McpAuthConfig,
    NoMcpAuthConfig,
    OAuthAuthorizationCodeMcpAuthConfig,
    OAuthClientCredentialsMcpAuthConfig,
    parse_mcp_auth_config,
)

__all__ = [
    "NoMcpAuthConfig",
    "ApiKeyMcpAuthConfig",
    "OAuthClientCredentialsMcpAuthConfig",
    "OAuthAuthorizationCodeMcpAuthConfig",
    "ApiKeyPerUserMcpAuthConfig",
    "McpAuthConfig",
    "parse_mcp_auth_config",
]
