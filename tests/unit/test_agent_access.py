"""Per-agent IM access config in the agent home (`access` block on `agent.yaml`)."""

import pytest
from pydantic import ValidationError

from fleetent.agent_config import AgentAccess, AgentFile, default_models, load_agent_home_file

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


def test_access_block_parses(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
access:
  allow_channels: ["C_ops", "C_eng"]
  allow_users: ["U_alice", "U_bob"]
  require_approval: false
""",
    )
    agent = load_agent_home_file(home)
    assert agent.access.allow_channels == ["C_ops", "C_eng"]
    assert agent.access.allow_users == ["U_alice", "U_bob"]
    assert agent.access.require_approval is False


def test_absent_access_block_defaults_closed(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
""",
    )
    agent = load_agent_home_file(home)
    # Safe default: no implicit allow, approval required.
    assert agent.access.allow_channels == []
    assert agent.access.allow_users == []
    assert agent.access.require_approval is True


def test_access_model_default_is_closed():
    access = AgentAccess()
    assert access.allow_channels == []
    assert access.allow_users == []
    assert access.require_approval is True


def test_access_block_rejects_unknown_field(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        """
name: alice
version: 1
"""
        + _MODELS
        + """
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
access:
  allow_users: ["U_alice"]
connectors:
  slack:
    bot_token_env: "xoxb-1234567890-abcdefghijklmnop"
    app_token_env: APP_TOKEN
""",
    )
    with pytest.raises(ValueError, match="inline secret"):
        load_agent_home_file(home)


def test_agentfile_default_access_closed():
    agent = AgentFile(name="alice", version=1, models=default_models())
    assert agent.access.require_approval is True
    assert agent.access.allow_users == []
