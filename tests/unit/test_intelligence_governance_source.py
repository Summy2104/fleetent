"""Intelligence config resolves from the active agent (runtime-read-agent-config).

Standalone single-agent processes read long_term_ctx config from the active agent;
multi-agent / no-agent indexes fall back to a neutral default agent's schema defaults.
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


def test_ltc_config_falls_back_to_default_without_agent() -> None:
    _publish_empty()
    cfg = ltcp._ltc_config()
    assert cfg.max_tokens == 2048  # LongTermContextSettings default


def test_kb_runtime_config_is_neutral_without_agent_source_construction() -> None:
    from fleetent.intelligence.knowledge_base import runtime as kb_runtime

    _publish_empty()
    assert kb_runtime._kb_config().default_kb_id == "global"  # schema default


def test_vector_configure_from_active_agent_uses_agent_embedding() -> None:
    from fleetent.config import EmbeddingSettings
    from fleetent.intelligence import vector_store
    from fleetent.intelligence.vector_store import runtime as vrt

    agent = AgentFile(
        name="a", version=1, embedding=EmbeddingSettings(backend="deterministic", dimensions=128)
    )
    _publish_single(agent)
    vector_store.configure_from_active_agent()
    # The embedding singleton is rebuilt from the agent's embedding block.
    assert vrt._embedding is not None
