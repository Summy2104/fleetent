"""Intelligence config resolves from the active agent (runtime-read-agent-config).

Standalone single-agent processes read long_term_ctx config from the active agent;
multi-agent / no-agent indexes fall back to a neutral default agent's schema defaults.
"""

import pytest

from fleetent import agent_config
from fleetent import long_term_ctx as ltcp
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import LongTermContextSettings
from fleetent.model import ModelConfigError
from fleetent.vector_store.embeddings import (
    DeterministicEmbeddingProvider,
    HttpEmbeddingProvider,
)


def _publish_single(agent: AgentFile) -> None:
    agent_config._index = AgentConfigIndex(agents={agent.name: agent}, default=agent.name)


def _publish_empty() -> None:
    agent_config._index = AgentConfigIndex(agents={}, default=None)


def test_ltc_config_from_active_agent() -> None:
    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        long_term_ctx=LongTermContextSettings(max_tokens=4242, memory_top_k=3),
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
    from fleetent.knowledge_base import runtime as kb_runtime

    _publish_empty()
    assert kb_runtime._kb_config().default_kb_id == "global"  # schema default


def test_vector_configure_from_active_agent_uses_agent_embedding() -> None:
    from fleetent import vector_store
    from fleetent.vector_store import runtime as vrt

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "embed",
                        "provider": "local",
                        "protocol": "http_embedding",
                        "endpoint": "http://embed.local/v1/embeddings",
                        "model": "bge",
                        "params": {"dimensions": 128},
                    }
                ],
                "routes": {"embedding": [{"target": "embed"}]},
            },
        }
    )
    _publish_single(agent)
    vector_store.configure_from_active_agent()
    # The embedding singleton is rebuilt from the agent's embedding block.
    assert vrt._embedding is not None


def test_vector_configure_from_active_agent_falls_back_without_embedding_route() -> None:
    from fleetent import vector_store
    from fleetent.vector_store import runtime as vrt

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "chat",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://llm.local/v1",
                        "model": "qwen",
                    }
                ],
                "routes": {"default": [{"target": "chat"}]},
            },
        }
    )
    _publish_single(agent)
    vector_store.configure_from_active_agent()
    assert isinstance(vrt._embedding, DeterministicEmbeddingProvider)


def test_vector_configure_from_active_agent_logs_warning_without_embedding_route(
    caplog,
) -> None:
    from fleetent import vector_store
    from fleetent.vector_store import runtime as vrt

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "chat",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://llm.local/v1",
                        "model": "qwen",
                    }
                ],
                "routes": {"default": [{"target": "chat"}]},
            },
        }
    )
    _publish_single(agent)
    with caplog.at_level("WARNING", logger="fleetent.vector_store.runtime"):
        vector_store.configure_from_active_agent()
    assert isinstance(vrt._embedding, DeterministicEmbeddingProvider)
    assert "falling back to deterministic embeddings" in caplog.text
    assert "Configure an embedding route for production use" in caplog.text


def test_vector_configure_from_active_agent_uses_http_embedding_without_warning(caplog) -> None:
    from fleetent import vector_store
    from fleetent.vector_store import runtime as vrt

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "embed",
                        "provider": "local",
                        "protocol": "http_embedding",
                        "endpoint": "http://embed.local/v1/embeddings",
                        "model": "bge",
                        "params": {"dimensions": 128},
                    }
                ],
                "routes": {"embedding": [{"target": "embed"}]},
            },
        }
    )
    _publish_single(agent)
    with caplog.at_level("WARNING", logger="fleetent.vector_store.runtime"):
        vector_store.configure_from_active_agent()
    assert isinstance(vrt._embedding, HttpEmbeddingProvider)
    assert caplog.text == ""


def test_vector_configure_from_active_agent_raises_for_misconfigured_embedding_route() -> None:
    from fleetent import vector_store

    agent = AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "embed",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://llm.local/v1",
                        "model": "qwen",
                    }
                ],
                "routes": {"embedding": [{"target": "embed"}]},
            },
        }
    )
    _publish_single(agent)
    with pytest.raises(ModelConfigError, match="unsupported protocol"):
        vector_store.configure_from_active_agent()
