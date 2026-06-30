"""Unit tests: connector 落库归一化 (_normalized_auth_config) 覆盖 oauth_authorization_code.

per-user OAuth 2.1 授权码类型的结构化非密字段 MUST 被持久化(不丢成空), 与既有
oauth_client_credentials / api_key_per_user 分支一致 (connector-per-user-oauth-ui).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleetent.platform.connector_management import connector_admin_api

_FULL = {
    "authorization_endpoint": "https://auth.internal/authorize",
    "token_url": "https://auth.internal/token",
    "client_id": "fleetent-crm",
    "client_secret_env": "CRM_OAUTH_SECRET",
    "scope": "mcp.read mcp.write",
    "redirect_path": "/oauth/callback",
}


def test_normalized_auth_config_persists_authorization_code_fields() -> None:
    out = connector_admin_api._normalized_auth_config("oauth_authorization_code", dict(_FULL))

    assert out != {}, "authorization_code 的结构化字段不得被丢弃"
    assert out["authorization_endpoint"] == "https://auth.internal/authorize"
    assert out["token_url"] == "https://auth.internal/token"
    assert out["client_id"] == "fleetent-crm"
    assert out["client_secret_env"] == "CRM_OAUTH_SECRET"
    assert out["scope"] == "mcp.read mcp.write"
    assert out["redirect_path"] == "/oauth/callback"


def test_create_body_keeps_authorization_code_auth_config() -> None:
    body = connector_admin_api.McpServerCreateBody(
        id="crm",
        transport="http",
        url="https://crm.internal/mcp",
        auth_type="oauth_authorization_code",
        auth_config=dict(_FULL),
    )

    assert body.auth_config["authorization_endpoint"] == "https://auth.internal/authorize"
    assert body.auth_config["client_id"] == "fleetent-crm"
    assert body.auth_config["redirect_path"] == "/oauth/callback"


def test_create_body_rejects_authorization_code_missing_required() -> None:
    # authorization_code 校验器要求 authorization_endpoint + token_url + client_id 非空
    with pytest.raises(ValidationError):
        connector_admin_api.McpServerCreateBody(
            id="crm",
            transport="http",
            url="https://crm.internal/mcp",
            auth_type="oauth_authorization_code",
            auth_config={"token_url": "https://auth.internal/token", "client_id": "x"},
        )
