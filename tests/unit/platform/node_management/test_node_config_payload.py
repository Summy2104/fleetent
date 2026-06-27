from __future__ import annotations

from pathlib import Path

import yaml

from fleetent.agent_config import AGENT_FILE_NAME, AgentFile, load_agent_file


def _agent_file_with_mcp() -> AgentFile:
    return AgentFile.model_validate(
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
        }
    )


def test_desired_state_payload_renders_mcp_servers_map() -> None:
    from fleetent.platform.agent_lifecycle import materialize

    payload = materialize.desired_state_payload_from_agent_file(_agent_file_with_mcp())

    # legacy list-of-id form must be gone; standard mcpServers map keyed by id is used
    assert "mcp_servers" not in payload
    assert set(payload["mcpServers"]) == {"docs"}
    assert payload["mcpServers"]["docs"]["url"] == "https://mcp.internal/docs"
    # env: references are non-secret variable-name pointers (like api_key_env) and are kept;
    # secret-bearing fields (plaintext env values, credential_ref) are stripped
    assert payload["mcpServers"]["docs"]["api_key_env"] == "DOCS_API_KEY"
    assert payload["mcpServers"]["docs"]["env"] == {"DOCS_TOKEN": "env:DOCS_TOKEN"}
    assert "credential_ref" not in payload["mcpServers"]["docs"]


def test_desired_state_payload_loads_back_into_agent_file(tmp_path: Path) -> None:
    from fleetent.platform.agent_lifecycle import materialize

    payload = materialize.desired_state_payload_from_agent_file(_agent_file_with_mcp())

    home = tmp_path / "support"
    home.mkdir()
    (home / AGENT_FILE_NAME).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    # node writes this payload as agent.yaml; the agent runtime must load it without
    # raising the legacy list-of-id `mcp_servers` ValueError.
    loaded = load_agent_file(home)
    assert [s.id for s in loaded.mcp_servers] == ["docs"]


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
    assert payload["mcpServers"]["docs"]["api_key_env"] == "DOCS_API_KEY"
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

    # env: reference survives (variable-name pointer); plaintext secret value is stripped
    assert payload["mcpServers"]["docs"]["env"] == {"DOCS_SHARED_TOKEN": "env:DOCS_SHARED_TOKEN"}
    assert "credential_ref" not in payload["mcpServers"]["docs"]
    assert "sk-inline-docs-secret" not in str(payload)


def test_desired_state_payload_env_ref_collected_by_node() -> None:
    from fleetent.platform.agent_lifecycle import materialize
    from fleetent.runtime.agent_init import referenced_env_names

    payload = materialize.desired_state_payload_from_agent_file(_agent_file_with_mcp())

    # node recomputes referenced env names from the delivered config; the preserved mcp
    # env: reference must be collected so ensure_env_scaffold scaffolds and fills it.
    names = referenced_env_names(AgentFile.model_validate(payload))
    assert "DOCS_TOKEN" in names
