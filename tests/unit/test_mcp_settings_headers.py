"""Tests for McpServerSettings.headers field and its passthrough to McpServerConfig."""

from __future__ import annotations

from pathlib import Path

from fleetent.agent_config import AgentFile, _reject_inline_secrets
from fleetent.config import McpServerSettings

_MODELS = {
    "targets": [
        {
            "id": "primary",
            "provider": "local",
            "protocol": "openai_chat",
            "base_url": "http://local.test/v1/",
            "model": "text",
        }
    ],
    "routes": {"default": [{"target": "primary"}]},
}


def test_mcp_server_settings_accepts_headers():
    s = McpServerSettings(
        id="middle",
        transport="http",
        url="https://middle.example/mcp",
        headers={"X-API-Key": "env:MIDDLE_KEY"},
    )
    assert s.headers == {"X-API-Key": "env:MIDDLE_KEY"}


def test_mcp_server_settings_headers_default_empty():
    s = McpServerSettings(id="x", transport="http", url="https://h/mcp")
    assert s.headers == {}


def test_agent_with_headers_loads_and_scan_passes():
    agent = AgentFile.model_validate(
        {
            "name": "t",
            "version": 1,
            "models": _MODELS,
            "mcpServers": {
                "middle": {
                    "transport": "http",
                    "url": "https://middle.example/mcp",
                    "headers": {"X-API-Key": "env:MIDDLE_KEY"},
                }
            },
        }
    )
    # headers preserved on the parsed model
    assert agent.mcp_servers[0].headers == {"X-API-Key": "env:MIDDLE_KEY"}
    # env: reference in a header value passes the inline-secret scan
    _reject_inline_secrets(agent, Path("agent.yaml"))
