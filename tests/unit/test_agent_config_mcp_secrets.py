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
    # Standard map-keyed form (key = server id); test bodies keep the legacy list shape.
    mapping = {}
    for entry in mcp_servers:
        entry = dict(entry)
        mapping[entry.pop("id")] = entry
    agent = AgentFile.model_validate(
        {"name": "t", "version": 1, "models": _MODELS, "mcpServers": mapping}
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


_USER_UUID = "5f5904ef-efcf-42bb-82fa-ad5a150b078c"


def _scan_im(im: dict) -> None:
    agent = AgentFile.model_validate({"name": "t", "version": 1, "models": _MODELS, "im": im})
    _reject_inline_secrets(agent, Path("agent.yaml"))


def test_im_access_allow_users_uuid_not_rejected():
    # Platform materializes internal user ids (UUIDs) into allow_users; a UUID's
    # length/entropy must not be flagged as an inline secret.
    _scan_im(
        {
            "supports_dm": True,
            "slack": {
                "bot_token_env": "SUPPORT_SLACK_BOT",
                "app_token_env": "SUPPORT_SLACK_APP",
                "access": {"allow_users": [_USER_UUID]},
            },
        }
    )


def test_im_access_allow_groups_uuid_not_rejected():
    # allow_groups on a telegram binding is an id list too — also exempt.
    _scan_im(
        {
            "supports_groups": True,
            "telegram": {
                "bot_token_env": "SUPPORT_TG_BOT",
                "access": {"allow_groups": [_USER_UUID]},
            },
        }
    )


def test_im_inline_bot_token_still_rejected():
    # The exemption must not relax scanning of secret-bearing im fields.
    with pytest.raises(ValueError, match="inline secret"):
        _scan_im(
            {
                "slack": {
                    "bot_token_env": _ATLASSIAN_TOKEN,
                    "app_token_env": "SUPPORT_SLACK_APP",
                }
            }
        )
