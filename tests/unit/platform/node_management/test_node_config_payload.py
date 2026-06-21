from __future__ import annotations

from fleetent.agent_config import AgentFile


def test_serialize_desired_state_payload_keeps_env_pointer_fields() -> None:
    from fleetent.platform.agent_lifecycle import materialize

    agent_file = AgentFile.model_validate(
        {
            "name": "support",
            "version": 3,
            "system_prompt": "Help users",
            "allowed_tools": ["shell"],
            "models": {
                "targets": [
                    {
                        "id": "default",
                        "provider": "anthropic",
                        "protocol": "openai_chat",
                        "base_url": "https://api.anthropic.test/v1",
                        "model": "claude-haiku",
                        "api_key_env": "SUPPORT_MODEL_KEY",
                    }
                ],
                "routes": {"default": [{"target": "default"}]},
            },
            "mcp_servers": [
                {
                    "id": "docs",
                    "transport": "http",
                    "url": "https://mcp.internal/docs",
                    "api_key_env": "DOCS_API_KEY",
                    "env": {"DOCS_TOKEN": "env:DOCS_TOKEN"},
                    "credential_ref": "env:DOCS_SHARED_SECRET",
                }
            ],
            "im": {
                "supports_dm": True,
                "slack": {
                    "bot_token_env": "SUPPORT_SLACK_BOT",
                    "app_token_env": "SUPPORT_SLACK_APP",
                    "access": {"allow_users": ["u1"]},
                },
            },
        }
    )

    payload = materialize.desired_state_payload_from_agent_file(agent_file)

    assert payload["name"] == "support"
    assert payload["system_prompt"] == "Help users"
    assert payload["models"]["targets"][0]["model"] == "claude-haiku"
    assert payload["models"]["targets"][0]["api_key_env"] == "SUPPORT_MODEL_KEY"
    assert payload["mcp_servers"][0]["api_key_env"] == "DOCS_API_KEY"
    assert "bot_token_env" in payload["im"]["slack"]
    assert "app_token_env" in payload["im"]["slack"]
    assert payload["im"]["slack"]["bot_token_env"] == "SUPPORT_SLACK_BOT"
    assert payload["im"]["slack"]["app_token_env"] == "SUPPORT_SLACK_APP"
    assert payload["im"]["supports_dm"] is True
    assert payload["im"]["slack"]["access"]["allow_users"] == ["u1"]


def test_serialize_desired_state_payload_still_strips_secret_values() -> None:
    from fleetent.platform.agent_lifecycle import materialize

    agent_file = AgentFile.model_validate(
        {
            "name": "support",
            "version": 3,
            "system_prompt": "Help users",
            "allowed_tools": ["shell"],
            "models": {
                "targets": [
                    {
                        "id": "default",
                        "provider": "anthropic",
                        "protocol": "openai_chat",
                        "base_url": "https://api.anthropic.test/v1",
                        "model": "claude-haiku",
                        "api_key_env": "SUPPORT_MODEL_KEY",
                    }
                ],
                "routes": {"default": [{"target": "default"}]},
            },
            "mcp_servers": [
                {
                    "id": "docs",
                    "transport": "http",
                    "url": "https://mcp.internal/docs",
                    "api_key_env": "DOCS_API_KEY",
                    "env": {
                        "DOCS_TOKEN": "sk-inline-docs-secret",
                        "DOCS_SHARED_TOKEN": "env:DOCS_SHARED_TOKEN",
                    },
                    "credential_ref": "env:DOCS_SHARED_SECRET",
                }
            ],
        }
    )

    payload = materialize.desired_state_payload_from_agent_file(agent_file)

    assert "env" not in payload["mcp_servers"][0]
    assert "credential_ref" not in payload["mcp_servers"][0]
    assert "sk-inline-docs-secret" not in str(payload)
