"""Unit: materialize 把 AgentFile dump 的 mcp_servers list 改写成标准 mcpServers map。"""

from __future__ import annotations

from types import SimpleNamespace

import fleetent.agent_store as agent_store
from fleetent.config import parse_mcp_servers
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.agent_lifecycle.materialize import _mcp_payload_to_map


def _server(**over):
    base = {
        "id": "docs",
        "transport": "http",
        "url": "https://docs/mcp",
        "auth_type": "none",
        "api_key_env": "",
        "command": "",
        "args": [],
        "env": {},
        "headers": {},
        "connect_timeout": 10.0,
        "call_timeout": 30.0,
        "degrade_mode": "degrade",
        "file_root": "",
        "file_isolation": "on",
        "auth": None,
        "approval_rules": [],
    }
    base.update(over)
    return base


def test_list_becomes_map_keyed_by_id() -> None:
    payload = {"name": "a", "mcp_servers": [_server()]}
    _mcp_payload_to_map(payload)
    assert "mcp_servers" not in payload
    assert set(payload["mcpServers"]) == {"docs"}
    assert payload["mcpServers"]["docs"]["url"] == "https://docs/mcp"
    # all-default fleetent fields are dropped (clean standard block, no x-fleetent)
    assert "x-fleetent" not in payload["mcpServers"]["docs"]


def test_nondefault_fleetent_fields_hoisted() -> None:
    payload = {
        "mcp_servers": [
            _server(
                id="billing",
                transport="stdio",
                command="/x",
                url="",
                degrade_mode="strict",
                file_root="/v",
                approval_rules=[{"tool": "charge", "when": None}],
            )
        ]
    }
    _mcp_payload_to_map(payload)
    ext = payload["mcpServers"]["billing"]["x-fleetent"]
    assert ext["degrade_mode"] == "strict"
    assert ext["file_root"] == "/v"
    assert ext["approval_rules"] == [{"tool": "charge", "when": None}]


def test_round_trips_through_parse() -> None:
    payload = {
        "mcp_servers": [
            _server(degrade_mode="strict", approval_rules=[{"tool": "t", "when": None}])
        ]
    }
    _mcp_payload_to_map(payload)
    servers = parse_mcp_servers(payload)
    assert servers[0].id == "docs"
    assert servers[0].degrade_mode == "strict"
    assert [r.tool for r in servers[0].approval_rules] == ["t"]


def test_no_mcp_servers_is_noop() -> None:
    payload = {"name": "a"}
    _mcp_payload_to_map(payload)
    assert "mcpServers" not in payload


def test_mcp_server_lookup_uses_binding_table_only(monkeypatch) -> None:
    monkeypatch.setattr(agent_store, "list_mcp_servers_for_agent", lambda _agent_id: ["github"])
    monkeypatch.setattr(
        materialize.mcp_server_store,
        "get_mcp_server",
        lambda agent_id, server_id: (
            {
                "transport": "stdio",
                "url": "",
                "auth_type": "none",
                "api_key_env": "",
                "command": "mcp-github",
                "args": [],
                "env": {},
                "headers": {},
            }
            if server_id == "github"
            else None
        ),
    )
    agent = SimpleNamespace(id=7, mcp_server_ids=["legacy-docs"])

    servers = materialize._mcp_servers_for_agent(agent)

    assert [server.id for server in servers] == ["github"]


def test_authorization_code_auth_config_materializes_to_auth_block(monkeypatch) -> None:
    monkeypatch.setattr(agent_store, "list_mcp_servers_for_agent", lambda _agent_id: ["crm"])
    monkeypatch.setattr(
        materialize.mcp_server_store,
        "get_mcp_server",
        lambda agent_id, server_id: {
            "transport": "http",
            "url": "https://crm/mcp",
            "auth_type": "oauth_authorization_code",
            "auth_config": {
                "authorization_endpoint": "https://auth.internal/authorize",
                "token_url": "https://auth.internal/token",
                "client_id": "fleetent-crm",
                "scope": "mcp.read",
                "redirect_path": "/oauth/callback",
                "client_secret_env": "CRM_OAUTH_SECRET",
            },
            "api_key_env": "",
            "command": "",
            "args": [],
            "env": {},
            "headers": {},
        },
    )
    agent = SimpleNamespace(id=9, mcp_server_ids=[])

    servers = materialize._mcp_servers_for_agent(agent)

    assert len(servers) == 1
    server = servers[0]
    assert server.auth_type == "oauth_authorization_code"
    assert server.auth is not None
    assert server.auth.grant == "authorization_code"
    assert server.auth.authorization_endpoint == "https://auth.internal/authorize"
    assert server.auth.token_url == "https://auth.internal/token"
    assert server.auth.client_id == "fleetent-crm"
    assert server.auth.redirect_path == "/oauth/callback"
    assert server.auth.client_secret_env == "CRM_OAUTH_SECRET"


def test_api_key_per_user_auth_config_materializes(monkeypatch) -> None:
    monkeypatch.setattr(agent_store, "list_mcp_servers_for_agent", lambda _agent_id: ["acme"])
    monkeypatch.setattr(
        materialize.mcp_server_store,
        "get_mcp_server",
        lambda agent_id, server_id: {
            "transport": "http",
            "url": "https://acme/mcp",
            "auth_type": "api_key_per_user",
            "auth_config": {"header_style": "x_api_key", "credential_input": "both"},
            "api_key_env": "",
            "command": "",
            "args": [],
            "env": {},
            "headers": {},
        },
    )
    agent = SimpleNamespace(id=11, mcp_server_ids=[])

    server = materialize._mcp_servers_for_agent(agent)[0]

    assert server.auth_type == "api_key_per_user"
    assert server.header_style == "x_api_key"
    assert server.credential_input == "both"
    assert server.auth is None  # no oauth block; secret is per-user, not here
    assert server.api_key_env == ""  # no static env key
