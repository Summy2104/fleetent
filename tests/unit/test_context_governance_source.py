"""Context compression config resolves from the active agent (runtime-read-agent-config).

When a config dict is not passed explicitly, compression resolves the agent's context_*
fields from the file index by agent_name; with no agent it falls back to Settings defaults.
"""

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.runtime import context


def _publish(agent: AgentFile) -> None:
    agent_config._index = AgentConfigIndex(
        agents={agent.name: agent}, by_channel={}, by_user={}, default=agent.name
    )


def test_default_config_from_agent(monkeypatch) -> None:
    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        context_max_tokens=12345,
        context_compress_threshold=0.5,
    )
    _publish(agent)
    cfg = context._default_config(agent_name="a")
    assert cfg["max_tokens"] == 12345


def test_default_config_falls_back_to_settings_without_agent() -> None:
    cfg = context._default_config(agent_name=None)
    assert cfg["max_tokens"] == 200_000  # Settings default


def test_default_config_unknown_agent_falls_back() -> None:
    agent_config._index = AgentConfigIndex(agents={}, by_channel={}, by_user={}, default=None)
    cfg = context._default_config(agent_name="missing")
    assert cfg["max_tokens"] == 200_000
