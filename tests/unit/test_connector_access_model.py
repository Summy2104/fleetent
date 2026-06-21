"""Tests for ImAccess model and connector restructuring (restructure-agent-access)."""

import pytest
from pydantic import ValidationError

from fleetent.agent_config import (
    AgentFile,
    ImAccess,
    SlackBinding,
    TelegramBinding,
    build_index,
    default_models,
)

_MODELS_YAML = """
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


def _agent_yaml(name: str, extra: str = "") -> str:
    return f"name: {name}\nversion: 1\n" + _MODELS_YAML + extra


# ── Task 1.1: ImAccess 默认值和字段约束 ────────────────────────────────


def test_connector_access_defaults():
    access = ImAccess()
    assert access.allow_groups == []
    assert access.allow_users == []
    assert access.require_approval is True


def test_connector_access_fields():
    access = ImAccess(
        allow_groups=["C1", "C2"],
        allow_users=["U1"],
        require_approval=False,
    )
    assert access.allow_groups == ["C1", "C2"]
    assert access.allow_users == ["U1"]
    assert access.require_approval is False


def test_connector_access_rejects_unknown_field():
    with pytest.raises((ValidationError, TypeError)):
        ImAccess(allow_everyone=True)  # type: ignore[call-arg]


# ── Task 1.2: SlackBinding 没有 channels 字段，有 access: ImAccess ──


def test_slack_connector_has_access_field():
    conn = SlackBinding(bot_token_env="BOT", app_token_env="APP")
    assert isinstance(conn.access, ImAccess)
    assert conn.access.require_approval is True


def test_slack_connector_no_channels_field():
    assert not hasattr(SlackBinding(bot_token_env="BOT", app_token_env="APP"), "channels")


def test_slack_connector_access_parsed():
    conn = SlackBinding(
        bot_token_env="BOT",
        app_token_env="APP",
        access=ImAccess(allow_groups=["C1"], allow_users=["U1"]),
    )
    assert conn.access.allow_groups == ["C1"]
    assert conn.access.allow_users == ["U1"]


def test_slack_connector_rejects_channels_field():
    with pytest.raises((ValidationError, TypeError)):
        SlackBinding(bot_token_env="BOT", app_token_env="APP", channels=["C1"])  # type: ignore[call-arg]


# ── Task 1.3: TelegramBinding 没有 channels 字段，有 access: ImAccess ──


def test_telegram_connector_has_access_field():
    conn = TelegramBinding(bot_token_env="BOT")
    assert isinstance(conn.access, ImAccess)
    assert conn.access.require_approval is True


def test_telegram_connector_no_channels_field():
    assert not hasattr(TelegramBinding(bot_token_env="BOT"), "channels")


def test_telegram_connector_access_parsed():
    conn = TelegramBinding(
        bot_token_env="BOT",
        access=ImAccess(allow_groups=["-100123"], require_approval=False),
    )
    assert conn.access.allow_groups == ["-100123"]
    assert conn.access.require_approval is False


def test_telegram_connector_rejects_channels_field():
    with pytest.raises((ValidationError, TypeError)):
        TelegramBinding(bot_token_env="BOT", channels=["-100"])  # type: ignore[call-arg]


# ── Task 1.4: AgentFile 无顶层 access；bindings 仅保留控制面 materialize 字段 ─────


def test_agentfile_bindings_defaults_to_control_plane_shape():
    agent = AgentFile(name="a", version=1, models=default_models())
    assert agent.bindings.default is False
    assert agent.bindings.users == []


def test_agentfile_has_no_access_field():
    agent = AgentFile(name="a", version=1, models=default_models())
    assert not hasattr(agent, "access")


def test_agentfile_rejects_legacy_bindings_channels_in_yaml(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        _agent_yaml("alice")
        + """
bindings:
  channels: ["slack:C1"]
""",
    )
    from fleetent.agent_config import load_agent_home_file

    with pytest.raises(ValidationError):
        load_agent_home_file(home)


def test_agentfile_accepts_materialized_bindings_default_in_yaml(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        _agent_yaml("alice")
        + """
bindings:
  default: true
  users: ["U1"]
""",
    )
    from fleetent.agent_config import load_agent_home_file

    agent = load_agent_home_file(home)
    assert agent.bindings.default is True
    assert agent.bindings.users == ["U1"]


def test_agentfile_rejects_top_level_access_in_yaml(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        _agent_yaml("alice")
        + """
access:
  allow_users: ["U1"]
""",
    )
    from fleetent.agent_config import load_agent_home_file

    with pytest.raises(ValidationError):
        load_agent_home_file(home)


def test_agentfile_connector_access_parsed_from_yaml(tmp_path):
    home = _write(
        tmp_path / "agent.yaml",
        _agent_yaml("alice")
        + """
im:
  slack:
    bot_token_env: BOT
    app_token_env: APP
    access:
      allow_groups: ["C1"]
      allow_users: ["U1"]
      require_approval: false
""",
    )
    from fleetent.agent_config import load_agent_home_file

    agent = load_agent_home_file(home)
    assert agent.im.slack is not None
    assert agent.im.slack.access.allow_groups == ["C1"]
    assert agent.im.slack.access.allow_users == ["U1"]
    assert agent.im.slack.access.require_approval is False


# ── Task 1.5: build_index() 不再读取 bindings 字段 ──────────────────────────


def _write_agent(agents_dir, name: str, extra: str = "") -> None:
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    _write(agent_dir / "agent.yaml", _agent_yaml(name) + extra)


def test_build_index_no_bindings(tmp_path):
    _write_agent(tmp_path, "support")
    _write_agent(tmp_path, "sales")
    index = build_index(tmp_path)
    assert set(index.agents.keys()) == {"support", "sales"}


def test_build_index_default_none_without_explicit_default(tmp_path):
    _write_agent(tmp_path, "support")
    index = build_index(tmp_path)
    assert index.default is None


# ── Task 1.6: AgentConfigIndex 不再有 by_channel/by_user/agent_for_channel/agent_for_user ──


def test_agent_config_index_no_by_channel(tmp_path):
    index = build_index(tmp_path)
    assert not hasattr(index, "by_channel")


def test_agent_config_index_no_by_user(tmp_path):
    index = build_index(tmp_path)
    assert not hasattr(index, "by_user")


def test_agent_config_index_no_agent_for_channel(tmp_path):
    index = build_index(tmp_path)
    assert not hasattr(index, "agent_for_channel")


def test_agent_config_index_no_agent_for_user(tmp_path):
    index = build_index(tmp_path)
    assert not hasattr(index, "agent_for_user")
