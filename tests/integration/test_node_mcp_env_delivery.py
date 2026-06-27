from __future__ import annotations

import httpx
import respx

from fleetent.agent_config import AgentFile
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState
from fleetent.node.reconcile import NodeReconciler
from fleetent.platform.agent_lifecycle import materialize


class _FakeBackend:
    """Minimal process backend: every agent is absent so reconcile writes home + spawns."""

    def __init__(self) -> None:
        self.spawn_calls: list[str] = []

    def spawn(self, agent_name: str, tenant_id: str = "default") -> None:
        self.spawn_calls.append(agent_name)

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:  # pragma: no cover
        pass

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        return None

    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        return None


def _agent_file_with_stdio_mcp() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "support",
            "version": 1,
            "tenant_id": "tenant-1",
            "system_prompt": "Help users",
            "models": {
                "targets": [
                    {
                        "id": "default",
                        "provider": "anthropic",
                        "protocol": "openai_chat",
                        "base_url": "https://api.anthropic.test/v1",
                        "model": "claude-haiku",
                    }
                ],
                "routes": {"default": [{"target": "default"}]},
            },
            "mcp_servers": [
                {
                    "id": "jira",
                    "transport": "stdio",
                    "command": "jira-mcp",
                    "env": {"JIRA_API_TOKEN": "env:JIRA_API_TOKEN"},
                }
            ],
        }
    )


@respx.mock
def test_managed_stdio_mcp_env_secret_reaches_dotenv(tmp_path) -> None:
    """End-to-end (platform render -> node reconcile -> .env): a stdio MCP server's
    ``env:`` reference must survive desired-state so node collects the var name and fills
    it from the secret channel into the agent ``.env``."""
    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    config = NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )
    # The platform render is the seam under test: it must keep the env: reference so the
    # downstream node cascade (referenced_env_names -> ensure_env_scaffold) can fill it.
    payload = materialize.desired_state_payload_from_agent_file(_agent_file_with_stdio_mcp())
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                tenant_id="tenant-1",
                config=payload,
                secrets={"JIRA_API_TOKEN": "jira-secret-value"},
            )
        ],
        source="remote",
    )

    NodeReconciler(config, _FakeBackend()).reconcile(desired)

    env_path = tmp_path / "tenants" / "tenant-1" / "agents" / "support" / ".env"
    env_text = env_path.read_text(encoding="utf-8")
    assert "JIRA_API_TOKEN=jira-secret-value" in env_text
