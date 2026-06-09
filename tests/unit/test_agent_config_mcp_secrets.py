"""Tests for inline-secret scanning scope and env: reference syntax in agent files.

Exercises _reject_inline_secrets directly (the scan runs in load_agent_file, not in
AgentFile.model_validate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.agent_config import AgentFile, _reject_inline_secrets

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

_ATLASSIAN_TOKEN = "ATATT3xFfGF0ZGXFtI5uUGu1MyRoPx_S6Udq0BRnF2M4XwhJB_sxUHiWAS3qxRFCmBa"


def _scan(mcp_servers: list[dict]) -> None:
    agent = AgentFile.model_validate(
        {"name": "t", "version": 1, "models": _MODELS, "mcp_servers": mcp_servers}
    )
    _reject_inline_secrets(agent, Path("agent.yaml"))


def test_npm_package_spec_in_args_not_rejected():
    # An npm package spec looks secret-ish but must not be flagged.
    _scan(
        [
            {
                "id": "jira",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@aashari/mcp-server-atlassian-jira"],
            }
        ]
    )


def test_env_ref_in_mcp_env_accepted():
    _scan(
        [
            {
                "id": "jira",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "pkg"],
                "env": {"ATLASSIAN_API_TOKEN": "env:JIRA_TOKEN"},
            }
        ]
    )


def test_literal_secret_in_mcp_env_rejected():
    with pytest.raises(ValueError, match="inline secret"):
        _scan(
            [
                {
                    "id": "jira",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "pkg"],
                    "env": {"ATLASSIAN_API_TOKEN": _ATLASSIAN_TOKEN},
                }
            ]
        )


def test_secret_embedded_in_url_still_rejected():
    # .url is still scanned — a token in the URL must be caught.
    with pytest.raises(ValueError, match="inline secret"):
        _scan(
            [
                {
                    "id": "remote",
                    "transport": "http",
                    "url": f"https://host/mcp?token={_ATLASSIAN_TOKEN}",
                }
            ]
        )
