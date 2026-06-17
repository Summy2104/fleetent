from __future__ import annotations

from fleetent.agent_config import AgentFile


def test_serialize_desired_state_payload_strips_secret_plumbing() -> None:
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
    assert "api_key_env" not in payload["models"]["targets"][0]
    assert "api_key_env" not in payload["mcp_servers"][0]
    assert "env" not in payload["mcp_servers"][0]
    assert "bot_token_env" not in payload["im"]["slack"]
    assert "app_token_env" not in payload["im"]["slack"]
    assert payload["im"]["supports_dm"] is True
    assert payload["im"]["slack"]["access"]["allow_users"] == ["u1"]
