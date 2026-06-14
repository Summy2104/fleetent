"""Per-connector IM access config in agent.yaml (`connectors.<platform>.access` block)."""

import pytest
from pydantic import ValidationError

from fleetent.agent_config import (
    AgentFile,
    ImAccess,
    ImBinding,
    SlackBinding,
    default_models,
    load_agent_home_file,
)

_MODELS = """
models:
  targets:
    - id: primary
      provider: local
      protocol: openai_chat
      base_url: http://local.test/v1/
      model: text
  routes:
    default:
      - target: primary
"""


def _write(path, body):
    path.write_text(body, encoding="utf-8")
    return path


def test_slack_access_block_parses(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
im:
  slack:
    bot_token_env: BOT_TOKEN
    app_token_env: APP_TOKEN
    access:
      allow_groups: ["C_ops", "C_eng"]
      allow_users: ["U_alice", "U_bob"]
      require_approval: false
""",
    )
    agent = load_agent_home_file(home)
    assert agent.im.slack is not None
    assert agent.im.slack.access.allow_groups == ["C_ops", "C_eng"]
    assert agent.im.slack.access.allow_users == ["U_alice", "U_bob"]
    assert agent.im.slack.access.require_approval is False


def test_absent_access_block_defaults_closed(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
im:
  slack:
    bot_token_env: BOT_TOKEN
    app_token_env: APP_TOKEN
""",
    )
    agent = load_agent_home_file(home)
    assert agent.im.slack is not None
    # Safe default: no implicit allow, approval required.
    assert agent.im.slack.access.allow_groups == []
    assert agent.im.slack.access.allow_users == []
    assert agent.im.slack.access.require_approval is True


def test_connector_access_model_default_is_closed():
    access = ImAccess()
    assert access.allow_groups == []
    assert access.allow_users == []
    assert access.require_approval is True


def test_slack_access_block_rejects_unknown_field(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
im:
  slack:
    bot_token_env: BOT_TOKEN
    app_token_env: APP_TOKEN
    access:
      allow_everyone: true
""",
    )
    with pytest.raises(ValidationError):
        load_agent_home_file(home)


def test_inline_secret_still_rejected_with_access_block(tmp_path):
    # The new access block must not weaken inline-secret rejection elsewhere.
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
im:
  slack:
    bot_token_env: "xoxb-1234567890-abcdefghijklmnop"
    app_token_env: APP_TOKEN
    access:
      allow_users: ["U_alice"]
""",
    )
    with pytest.raises(ValueError, match="inline secret"):
        load_agent_home_file(home)


def test_agentfile_default_connector_access_closed():
    agent = AgentFile(
        name="alice",
        version=1,
        models=default_models(),
        im=ImBinding(slack=SlackBinding(bot_token_env="BOT", app_token_env="APP")),
    )
    assert agent.im.slack is not None
    assert agent.im.slack.access.require_approval is True
    assert agent.im.slack.access.allow_users == []


def test_telegram_access_block_parses(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
im:
  telegram:
    bot_token_env: TG_BOT_TOKEN
    access:
      allow_users: ["12345"]
      require_approval: false
""",
    )
    agent = load_agent_home_file(home)
    assert agent.im.telegram is not None
    assert agent.im.telegram.access.allow_users == ["12345"]
    assert agent.im.telegram.access.require_approval is False


def test_agentfile_with_connector_access_via_constructor():
    agent = AgentFile(
        name="alice",
        version=1,
        models=default_models(),
        im=ImBinding(
            slack=SlackBinding(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ImAccess(allow_users=["U_alice"], require_approval=False),
            )
        ),
    )
    assert agent.im.slack is not None
    assert agent.im.slack.access.allow_users == ["U_alice"]
    assert agent.im.slack.access.require_approval is False
