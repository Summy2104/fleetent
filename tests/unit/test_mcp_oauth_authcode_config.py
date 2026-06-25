"""Unit: agent.yaml ``mcp_servers[].auth`` 解析支持 authorization_code(用户委托)grant。

覆盖 McpOAuthSettings 新增 authorization_code 字段、parse_mcp_servers 透传、
McpServerConfig.from_settings 映射,以及缺关键字段时的清晰报错。client_credentials
既有配置与映射行为必须完全不变(回归)。

纯配置解析/校验——不碰真实 DB / FastAPI / 网络。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleetent.config import McpOAuthSettings, McpServerSettings, parse_mcp_servers
from fleetent.integrations.mcp.client import McpServerConfig

# ── McpOAuthSettings: grant 默认与 authorization_code 字段 ──────────────────────


def test_oauth_settings_default_grant_is_client_credentials() -> None:
    # 未声明 grant 的既有配置默认机器身份,保持现状不破坏。
    s = McpOAuthSettings(
        type="oauth2",
        token_url="https://auth.internal/token",
        client_id="cid",
        client_secret_env="SECRET",
        scope="mcp.read",
    )
    assert s.grant == "client_credentials"
    assert s.authorization_endpoint == ""
    assert s.redirect_path == ""


def test_oauth_settings_authorization_code_fields() -> None:
    s = McpOAuthSettings(
        type="oauth2",
        grant="authorization_code",
        authorization_endpoint="https://auth.internal/authorize",
        token_url="https://auth.internal/token",
        client_id="cid",
        client_secret_env="SECRET",
        scope="mcp.read mcp.write",
        redirect_path="/oauth/callback",
    )
    assert s.grant == "authorization_code"
    assert s.authorization_endpoint == "https://auth.internal/authorize"
    assert s.token_url == "https://auth.internal/token"
    assert s.redirect_path == "/oauth/callback"


def test_oauth_settings_authorization_code_missing_authorization_endpoint_rejected() -> None:
    with pytest.raises(ValidationError, match="authorization_endpoint"):
        McpOAuthSettings(
            type="oauth2",
            grant="authorization_code",
            token_url="https://auth.internal/token",
            client_id="cid",
        )


def test_oauth_settings_authorization_code_missing_client_id_rejected() -> None:
    with pytest.raises(ValidationError, match="client_id"):
        McpOAuthSettings(
            type="oauth2",
            grant="authorization_code",
            authorization_endpoint="https://auth.internal/authorize",
            token_url="https://auth.internal/token",
        )


def test_oauth_settings_authorization_code_missing_token_url_rejected() -> None:
    with pytest.raises(ValidationError, match="token_url"):
        McpOAuthSettings(
            type="oauth2",
            grant="authorization_code",
            authorization_endpoint="https://auth.internal/authorize",
            client_id="cid",
        )


def test_oauth_settings_unknown_grant_rejected() -> None:
    with pytest.raises(ValidationError):
        McpOAuthSettings(type="oauth2", grant="implicit")


def test_oauth_settings_client_credentials_tolerates_empty_authcode_fields() -> None:
    # client_credentials 不要求 authorization_endpoint / redirect_path。
    s = McpOAuthSettings(type="oauth2", grant="client_credentials", token_url="https://a/t")
    assert s.authorization_endpoint == ""


# ── parse_mcp_servers 透传 authorization_code 配置 ─────────────────────────────


def _by_id(servers: list[McpServerSettings]) -> dict[str, McpServerSettings]:
    return {s.id: s for s in servers}


def test_parse_authorization_code_block() -> None:
    raw = {
        "mcpServers": {
            "crm": {
                "url": "https://crm.internal/mcp",
                "x-fleetent": {
                    "auth": {
                        "type": "oauth2",
                        "grant": "authorization_code",
                        "authorization_endpoint": "https://auth.internal/authorize",
                        "token_url": "https://auth.internal/token",
                        "client_id": "fleetent-crm",
                        "client_secret_env": "CRM_OAUTH_SECRET",
                        "scope": "mcp.read",
                        "redirect_path": "/oauth/callback",
                    }
                },
            }
        }
    }
    s = _by_id(parse_mcp_servers(raw))["crm"]
    assert s.auth is not None
    assert s.auth.grant == "authorization_code"
    assert s.auth.authorization_endpoint == "https://auth.internal/authorize"
    assert s.auth.redirect_path == "/oauth/callback"


# ── from_settings 映射 ────────────────────────────────────────────────────────


def test_from_settings_maps_authorization_code() -> None:
    s = McpServerSettings(
        id="crm",
        transport="http",
        url="https://crm.internal/mcp",
        auth=McpOAuthSettings(
            type="oauth2",
            grant="authorization_code",
            authorization_endpoint="https://auth.internal/authorize",
            token_url="https://auth.internal/token",
            client_id="fleetent-crm",
            client_secret_env="CRM_SECRET",
            scope="mcp.read",
            redirect_path="/oauth/callback",
        ),
    )
    c = McpServerConfig.from_settings(s)
    assert c.auth_type == "oauth2"
    assert c.oauth_grant == "authorization_code"
    assert c.authorization_endpoint == "https://auth.internal/authorize"
    assert c.token_url == "https://auth.internal/token"
    assert c.client_id == "fleetent-crm"
    assert c.client_secret_env == "CRM_SECRET"
    assert c.scope == "mcp.read"
    assert c.redirect_path == "/oauth/callback"


def test_from_settings_client_credentials_grant_unchanged() -> None:
    # 回归:既有 client_credentials 配置映射的所有字段与默认 grant 保持现状。
    s = McpServerSettings(
        id="crm",
        transport="http",
        url="https://crm.internal/mcp",
        auth=McpOAuthSettings(
            type="oauth2",
            token_url="https://auth.internal/token",
            client_id="fleetent-crm",
            client_secret_env="CRM_SECRET",
            scope="mcp.read",
        ),
    )
    c = McpServerConfig.from_settings(s)
    assert c.auth_type == "oauth2"
    assert c.oauth_grant == "client_credentials"
    assert c.authorization_endpoint == ""
    assert c.redirect_path == ""
    assert c.token_url == "https://auth.internal/token"
    assert c.client_id == "fleetent-crm"


def test_from_settings_no_auth_defaults() -> None:
    s = McpServerSettings(id="docs", transport="http", url="https://docs/mcp")
    c = McpServerConfig.from_settings(s)
    assert c.auth_type == "none"
    assert c.oauth_grant == "client_credentials"
    assert c.authorization_endpoint == ""
    assert c.redirect_path == ""
