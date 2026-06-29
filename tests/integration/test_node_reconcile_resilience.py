"""Integration test: node reconcile platform-down resilience (task 3.2 / D5).

When the platform is unreachable and the cache has no secrets, an agent that was
previously materialized (.env contains real values) must be spawnable from disk —
without being deferred by the 'no secrets from cache' gate.
"""

from __future__ import annotations

import httpx
import respx
import yaml

from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _agent_config() -> dict:
    return {
        "name": "support",
        "version": 1,
        "system_prompt": "You are support.",
        "models": {
            "targets": [
                {
                    "id": "primary",
                    "provider": "anthropic",
                    "protocol": "openai_chat",
                    "base_url": "https://api.anthropic.com/v1/",
                    "model": "claude-opus-4-8",
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
            ],
            "routes": {"default": [{"target": "primary"}]},
        },
    }


class FakeBackend:
    def __init__(self, alive: dict[str, int | None]) -> None:
        self.alive = alive
        self.spawn_calls: list[str] = []
        self.stop_calls: list[str] = []

    def spawn(self, agent_name: str, tenant_id: str = "default") -> None:
        del tenant_id
        self.spawn_calls.append(agent_name)

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:
        del tenant_id
        self.stop_calls.append(agent_name)

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        del tenant_id
        return self.alive.get(agent_name)

    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        del agent_name, tenant_id
        return None


@respx.mock
def test_reconcile_restarts_from_env_when_platform_down(tmp_path) -> None:
    """Agent with a materialized .env can restart when platform is unreachable."""
    from fleetent.node.reconcile import NodeReconciler

    respx.post("https://platform.internal/nodes/node-a/status").mock(
        side_effect=httpx.ConnectError("status-down")
    )

    # Step 1: Agent home with a complete .env (previously materialized with real secrets)
    home = tmp_path / "tenants" / "default" / "agents" / "support"
    home.mkdir(parents=True)
    home.chmod(0o700)
    (home / "agent.yaml").write_text(
        yaml.safe_dump(_agent_config(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    env_path = home / ".env"
    env_path.write_text(
        "ANTHROPIC_API_KEY=sk-live-secret\nFLEETENT_TUI_TOKEN=ma-" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    # Step 2: Platform is down → cache fallback, secrets stripped (empty)
    cached_state = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config=_agent_config(),
                secrets={},  # cache has no secrets
                tenant_id="default",
            )
        ],
        source="cache",
    )

    # Agent has crashed (pid=None) but .env has real secrets from prior materialization
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(cached_state)

    # Must spawn — not deferred — because .env has real values
    assert backend.spawn_calls == ["support"], (
        "Expected reconcile to spawn agent from existing .env, but it was deferred"
    )


@respx.mock
def test_reconcile_rewrites_home_for_kb_resync_without_respawn(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    home = tmp_path / "tenants" / "default" / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(
        yaml.safe_dump(_agent_config(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    backend = FakeBackend({"support": 12345})
    desired_config = _agent_config() | {
        "knowledge": {
            "enabled": True,
            "bindings": [{"tenant_id": "default", "kb_id": "support-kb", "default": True}],
        }
    }
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config=desired_config,
                secrets={},
                tenant_id="default",
                knowledge_resync_epoch="1",
            )
        ],
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert backend.stop_calls == []
    assert backend.spawn_calls == []
    updated = yaml.safe_load((home / "agent.yaml").read_text(encoding="utf-8"))
    assert updated["knowledge"]["bindings"][0]["kb_id"] == "support-kb"
