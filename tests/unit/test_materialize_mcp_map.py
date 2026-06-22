"""Unit: materialize 把 AgentFile dump 的 mcp_servers list 改写成标准 mcpServers map。"""

from __future__ import annotations

from fleetent.config import parse_mcp_servers
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
