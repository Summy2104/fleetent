from typing import Any

import pytest

from fleetent.agent_config import AgentFile


def _agent() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "support",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "primary",
                        "provider": "anthropic",
                        "protocol": "openai_chat",
                        "base_url": "https://primary.test/v1/",
                        "model": "claude-sonnet",
                        "api_key_env": "FLEETENT_MODEL_PRIMARY_API_KEY",
                        "max_tokens": 4096,
                        "params": {"temperature": 0.5, "top_p": 0.9},
                    },
                    {
                        "id": "backup",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://backup.test/v1/",
                        "model": "llama",
                        "max_tokens": 2048,
                        "params": {"temperature": 0.2},
                    },
                    {
                        "id": "image",
                        "provider": "local",
                        "protocol": "openai_image_generation",
                        "endpoint": "http://image.test/v1/images/generations",
                        "model": "flux",
                    },
                    {
                        "id": "embed",
                        "provider": "local",
                        "protocol": "http_embedding",
                        "endpoint": "http://embed.test/v1/embeddings",
                        "model": "bge",
                    },
                    {
                        "id": "rerank",
                        "provider": "local",
                        "protocol": "http_rerank",
                        "endpoint": "http://rerank.test/v1/rerank",
                        "model": "bge-reranker",
                    },
                ],
                "routes": {
                    "default": [
                        {
                            "target": "primary",
                            "max_tokens": 1024,
                            "params": {"temperature": 0},
                        },
                        {"target": "backup"},
                    ],
                    "image_generation": [{"target": "image"}],
                    "embedding": [{"target": "embed"}],
                    "rerank": [{"target": "rerank"}],
                },
            },
        }
    )


def test_model_policy_snapshot_resolves_route_chain_in_order() -> None:
    from fleetent.model import ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(_agent())

    chain = policy.resolve("default")

    assert [entry.target_id for entry in chain] == ["primary", "backup"]
    assert chain[0].base_url == "https://primary.test/v1/"
    assert chain[1].base_url == "http://backup.test/v1/"


def test_model_policy_snapshot_merges_route_overrides() -> None:
    from fleetent.model import ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(_agent())

    first = policy.resolve("default")[0]

    assert first.max_tokens == 1024
    assert first.params == {"temperature": 0, "top_p": 0.9}


def test_model_policy_snapshot_omits_plaintext_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.model import ModelPolicySnapshot

    monkeypatch.setenv("FLEETENT_MODEL_PRIMARY_API_KEY", "sk-real-secret")

    dumped = ModelPolicySnapshot.from_agent(_agent()).model_dump()

    assert "sk-real-secret" not in repr(dumped)
    assert dumped["targets"]["primary"]["api_key_env"] == "FLEETENT_MODEL_PRIMARY_API_KEY"


def test_resolver_requires_declared_env_before_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.model import ModelConfigError, ModelPolicySnapshot

    monkeypatch.delenv("FLEETENT_MODEL_PRIMARY_API_KEY", raising=False)
    policy = ModelPolicySnapshot.from_agent(_agent())

    with pytest.raises(ModelConfigError, match="FLEETENT_MODEL_PRIMARY_API_KEY"):
        policy.require_api_key(policy.resolve("default")[0])


@pytest.mark.parametrize("route_key", ["image_generation", "embedding", "rerank"])
def test_service_routes_resolve_from_same_agent_policy(route_key: str) -> None:
    from fleetent.model import ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(_agent())

    resolved = policy.resolve(route_key)[0]

    assert resolved.route_key == route_key
    assert resolved.agent_id == "support"
    assert resolved.endpoint is not None


async def test_call_with_policy_fallbacks_on_switchable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.model import ModelCallSwitchableError, ModelPolicySnapshot, call_with_policy

    monkeypatch.setenv("FLEETENT_MODEL_PRIMARY_API_KEY", "test-key")
    policy = ModelPolicySnapshot.from_agent(_agent())
    calls: list[str] = []

    async def caller(resolved: Any) -> str:
        calls.append(resolved.target_id)
        if resolved.target_id == "primary":
            raise ModelCallSwitchableError("rate limited")
        return "ok"

    assert await call_with_policy(policy, "default", caller) == "ok"
    assert calls == ["primary", "backup"]


async def test_call_with_policy_does_not_fallback_on_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.model import ModelConfigError, ModelPolicySnapshot, call_with_policy

    monkeypatch.delenv("FLEETENT_MODEL_PRIMARY_API_KEY", raising=False)
    policy = ModelPolicySnapshot.from_agent(_agent())
    calls: list[str] = []

    async def caller(resolved: Any) -> str:
        calls.append(resolved.target_id)
        return "ok"

    with pytest.raises(ModelConfigError):
        await call_with_policy(policy, "default", caller)

    assert calls == []
