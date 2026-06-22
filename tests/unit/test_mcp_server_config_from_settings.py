"""Unit: McpServerSettings -> McpServerConfig 映射(含 x-fleetent 扩展与自托管 OAuth)。"""

from __future__ import annotations

from fleetent.config import McpApprovalRule, McpOAuthSettings, McpServerSettings
from fleetent.integrations.mcp.client import McpServerConfig


def test_from_settings_maps_core_and_extensions() -> None:
    s = McpServerSettings(
        id="billing",
        transport="stdio",
        command="/bin/billing",
        args=["--ro"],
        env={"A": "1"},
        degrade_mode="strict",
        file_root="/var/out",
        file_isolation="off",
        approval_rules=[McpApprovalRule(tool="charge_card")],
    )
    c = McpServerConfig.from_settings(s)
    assert c.id == "billing"
    assert c.transport == "stdio"
    assert c.command == "/bin/billing"
    assert c.args == ["--ro"]
    assert c.degrade_mode == "strict"
    assert c.file_root == "/var/out"
    assert c.file_isolation == "off"
    assert [r.tool for r in c.approval_rules] == ["charge_card"]


def test_from_settings_self_hosted_oauth() -> None:
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
    assert c.token_url == "https://auth.internal/token"
    assert c.client_id == "fleetent-crm"
    assert c.client_secret_env == "CRM_SECRET"
    assert c.scope == "mcp.read"


def test_from_settings_header_auth_default() -> None:
    s = McpServerSettings(id="docs", transport="http", url="https://docs/mcp")
    c = McpServerConfig.from_settings(s)
    assert c.auth_type == "none"
