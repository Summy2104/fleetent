"""Unit: 标准 mcpServers map 配置解析 + x-fleetent 扩展 + transport 自动判定 + ${VAR}.

覆盖 mcp-config-standardization 的配置解析层(config.parse_mcp_servers):
- 顶层 mcpServers / mcp_servers 两种 key 的 map 解析(key = server id)
- transport 自动判定(command→stdio,url→remote)
- ${VAR} 环境引用展开
- x-fleetent 扩展块(degrade_mode/file_root/file_isolation/auth/approval_rules)
- legacy list-of-id 形式被拒
"""

from __future__ import annotations

import pytest

from fleetent.config import parse_mcp_servers


def _by_id(servers):
    return {s.id: s for s in servers}


def test_mcpservers_map_key_becomes_id() -> None:
    raw = {"mcpServers": {"github": {"command": "npx", "args": ["-y", "srv"]}}}
    servers = _by_id(parse_mcp_servers(raw))
    assert "github" in servers
    assert servers["github"].command == "npx"
    assert servers["github"].args == ["-y", "srv"]


def test_snake_case_top_key_also_accepted() -> None:
    raw = {"mcp_servers": {"docs": {"url": "https://docs.internal/mcp"}}}
    servers = _by_id(parse_mcp_servers(raw))
    assert "docs" in servers


def test_transport_autodetect_stdio() -> None:
    raw = {"mcpServers": {"local": {"command": "/bin/srv"}}}
    assert _by_id(parse_mcp_servers(raw))["local"].transport == "stdio"


def test_transport_autodetect_remote() -> None:
    raw = {"mcpServers": {"remote": {"url": "https://x.internal/mcp"}}}
    assert _by_id(parse_mcp_servers(raw))["remote"].transport == "http"


def test_env_var_expansion(monkeypatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "secret-123")
    raw = {
        "mcpServers": {
            "remote": {
                "url": "https://x.internal/mcp",
                "headers": {"Authorization": "Bearer ${MY_TOKEN}"},
            }
        }
    }
    servers = _by_id(parse_mcp_servers(raw))
    assert servers["remote"].headers["Authorization"] == "Bearer secret-123"


def test_x_fleetent_extension_hoisted() -> None:
    raw = {
        "mcpServers": {
            "billing": {
                "command": "/bin/billing",
                "x-fleetent": {
                    "degrade_mode": "strict",
                    "file_root": "/var/lib/billing/out",
                    "file_isolation": "on",
                    "approval_rules": [{"tool": "charge_card"}],
                },
            }
        }
    }
    s = _by_id(parse_mcp_servers(raw))["billing"]
    assert s.degrade_mode == "strict"
    assert s.file_root == "/var/lib/billing/out"
    assert s.file_isolation == "on"
    assert [r.tool for r in s.approval_rules] == ["charge_card"]


def test_x_fleetent_self_hosted_oauth() -> None:
    raw = {
        "mcpServers": {
            "crm": {
                "url": "https://crm.internal/mcp",
                "x-fleetent": {
                    "auth": {
                        "type": "oauth2",
                        "token_url": "https://auth.internal/oauth/token",
                        "client_id": "fleetent-crm",
                        "client_secret_env": "CRM_OAUTH_SECRET",
                        "scope": "mcp.read",
                    }
                },
            }
        }
    }
    s = _by_id(parse_mcp_servers(raw))["crm"]
    assert s.auth is not None
    assert s.auth.type == "oauth2"
    assert s.auth.token_url == "https://auth.internal/oauth/token"
    assert s.auth.client_secret_env == "CRM_OAUTH_SECRET"


def test_legacy_list_form_rejected() -> None:
    raw = {"mcp_servers": [{"id": "github", "command": "npx"}]}
    with pytest.raises((ValueError, TypeError)):
        parse_mcp_servers(raw)
