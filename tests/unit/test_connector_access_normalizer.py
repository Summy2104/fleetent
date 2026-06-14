"""Tests for _get_connector_access and the simplified default-agent resolver."""

from fleetent.agent_config import (
    AgentConnectors,
    AgentFile,
    ConnectorAccess,
    SlackConnector,
    TelegramConnector,
    default_models,
)
from fleetent.im_gateway.normalizer import _get_connector_access, get_agent_for_context


def _agent_with_connectors(
    slack_access: ConnectorAccess | None = None,
    telegram_access: ConnectorAccess | None = None,
) -> AgentFile:
    slack = (
        SlackConnector(bot_token_env="BOT", app_token_env="APP", access=slack_access)
        if slack_access is not None
        else SlackConnector(bot_token_env="BOT", app_token_env="APP")
    )
    telegram = (
        TelegramConnector(bot_token_env="BOT", access=telegram_access)
        if telegram_access is not None
        else None
    )
    return AgentFile(
        name="test",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(slack=slack, telegram=telegram),
    )


# ── Task 3.1: _get_connector_access 按 platform 返回正确 connector 的 access ──


def test_get_connector_access_slack():
    slack_access = ConnectorAccess(allow_users=["U1"])
    agent = _agent_with_connectors(slack_access=slack_access)
    result = _get_connector_access(agent, "slack")
    assert result.allow_users == ["U1"]


def test_get_connector_access_telegram():
    tg_access = ConnectorAccess(allow_channels=["-100"])
    agent = AgentFile(
        name="test",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            telegram=TelegramConnector(bot_token_env="BOT", access=tg_access)
        ),
    )
    result = _get_connector_access(agent, "telegram")
    assert result.allow_channels == ["-100"]


# ── Task 3.2: _get_connector_access 对未知 platform 返回 ConnectorAccess() 默认关闭 ──


def test_get_connector_access_unknown_platform_returns_default_closed():
    agent = _agent_with_connectors()
    result = _get_connector_access(agent, "whatsapp")
    assert result.allow_channels == []
    assert result.allow_users == []
    assert result.require_approval is True


def test_get_connector_access_none_agent_returns_default_closed():
    result = _get_connector_access(None, "slack")
    assert result.allow_channels == []
    assert result.allow_users == []
    assert result.require_approval is True


# ── Task 3.3: get_agent_for_context 简化后仅返回 default agent ──────────────


def test_get_agent_for_context_returns_default(monkeypatch):
    import fleetent.agent_config as ac

    default_agent = AgentFile(name="default", version=1, models=default_models())
    from fleetent.agent_config import AgentConfigIndex

    fake_index = AgentConfigIndex(agents={"default": default_agent}, default="default")
    monkeypatch.setattr(ac, "_index", fake_index)

    result = get_agent_for_context()
    assert result is not None
    assert result.name == "default"


def test_get_agent_for_context_no_channel_lookup(monkeypatch):
    """Channel is ignored; only default matters."""
    import fleetent.agent_config as ac

    default_agent = AgentFile(name="default", version=1, models=default_models())
    other_agent = AgentFile(name="other", version=1, models=default_models())
    from fleetent.agent_config import AgentConfigIndex

    # "other" has no routing — only "default" is the default
    fake_index = AgentConfigIndex(
        agents={"default": default_agent, "other": other_agent}, default="default"
    )
    monkeypatch.setattr(ac, "_index", fake_index)

    result = get_agent_for_context()
    assert result is not None
    assert result.name == "default"


def test_get_agent_for_context_none_when_no_default(monkeypatch):
    import fleetent.agent_config as ac
    from fleetent.agent_config import AgentConfigIndex

    fake_index = AgentConfigIndex(agents={}, default=None)
    monkeypatch.setattr(ac, "_index", fake_index)

    result = get_agent_for_context()
    assert result is None
