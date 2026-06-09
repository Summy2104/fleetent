"""Tests for MCP client env: reference resolution (stdio env + http headers),
protocol version, and URL-verbatim handling."""

from __future__ import annotations

from fleetent.integrations.mcp import client as mcp_client
from fleetent.integrations.mcp.client import PROTOCOL_VERSION, McpServerConfig

# ── _resolve_env_ref ──────────────────────────────────────────────────────────


def test_resolve_env_ref_resolves_from_environ(monkeypatch):
    monkeypatch.setenv("FLEETENT_TEST_TOK", "secret-value")
    assert mcp_client._resolve_env_ref("env:FLEETENT_TEST_TOK") == "secret-value"


def test_resolve_env_ref_literal_passthrough():
    assert mcp_client._resolve_env_ref("plain-literal") == "plain-literal"


def test_resolve_env_ref_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("FLEETENT_TEST_MISSING", raising=False)
    assert mcp_client._resolve_env_ref("env:FLEETENT_TEST_MISSING") == ""


# ── _subprocess_env resolves env: ─────────────────────────────────────────────


def test_subprocess_env_resolves_env_ref(monkeypatch):
    monkeypatch.setenv("JIRA_TOKEN_X", "jira-real-token")
    server = McpServerConfig(
        id="jira",
        transport="stdio",
        command="npx",
        args=["-y", "pkg"],
        env={"ATLASSIAN_API_TOKEN": "env:JIRA_TOKEN_X", "PLAIN": "literal"},
    )
    env = mcp_client._subprocess_env(server)
    assert env["ATLASSIAN_API_TOKEN"] == "jira-real-token"
    assert env["PLAIN"] == "literal"


# ── _base_headers resolves env: in header values ──────────────────────────────


def test_base_headers_resolves_env_ref(monkeypatch):
    monkeypatch.setenv("MIDDLE_KEY_X", "middle-real-key")
    server = McpServerConfig(
        id="middle",
        transport="http",
        url="https://middle.example/mcp",
        headers={"X-API-Key": "env:MIDDLE_KEY_X", "X-Static": "stay"},
    )
    headers = mcp_client._base_headers(server)
    assert headers["X-API-Key"] == "middle-real-key"
    assert headers["X-Static"] == "stay"


# ── protocol version ──────────────────────────────────────────────────────────


def test_protocol_version_is_latest():
    assert PROTOCOL_VERSION == "2025-11-25"
