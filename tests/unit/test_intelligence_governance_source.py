"""Intelligence config resolves from the active agent (runtime-read-agent-config).

Standalone single-agent processes read long_term_ctx / KB config from the active agent;
multi-agent / no-agent indexes fall back to Settings defaults.
"""

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile
from fleetent.config import LongTermContextSettings
from fleetent.intelligence import long_term_ctx as ltcp


def _publish_single(agent: AgentFile) -> None:
    agent_config._index = AgentConfigIndex(
        agents={agent.name: agent}, by_channel={}, by_user={}, default=agent.name
    )


def _publish_empty() -> None:
    agent_config._index = AgentConfigIndex(agents={}, by_channel={}, by_user={}, default=None)


def test_ltc_config_from_active_agent() -> None:
    agent = AgentFile(
        name="a", version=1, long_term_ctx=LongTermContextSettings(max_tokens=4242, memory_top_k=3)
    )
    _publish_single(agent)
    cfg = ltcp._ltc_config()
    assert cfg.max_tokens == 4242
    assert cfg.memory_top_k == 3


def test_ltc_config_falls_back_to_settings_without_agent() -> None:
    _publish_empty()
    cfg = ltcp._ltc_config()
    assert cfg.max_tokens == 2048  # LongTermContextSettings default
