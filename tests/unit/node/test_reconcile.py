from __future__ import annotations

import hashlib
import json

import httpx
import respx
import yaml

from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState


class FakeBackend:
    def __init__(
        self,
        alive: dict[str, int | None],
        gateway_ports: dict[str, int | None] | None = None,
    ) -> None:
        self.alive = alive
        self.gateway_ports = gateway_ports or {}
        self.spawn_calls: list[str] = []
        self.stop_calls: list[str] = []

    def spawn(self, agent_name: str) -> None:
        self.spawn_calls.append(agent_name)

    def stop(self, agent_name: str) -> None:
        self.stop_calls.append(agent_name)

    def is_alive(self, agent_name: str) -> int | None:
        return self.alive.get(agent_name)

    def gateway_port(self, agent_name: str) -> int | None:
        return self.gateway_ports.get(agent_name)


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _desired(
    config: dict[str, object] | None = None,
    secrets: dict[str, str] | None = None,
    source: str = "remote",
) -> DesiredState:
    return DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config=config or {"name": "support"},
                secrets=secrets or {},
            )
        ],
        source=source,
    )


def _post_body(route: respx.Route) -> dict[str, object]:
    return json.loads(route.calls[0].request.content)


@respx.mock
def test_reconcile_spawns_missing_desired_agent_after_writing_home(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    backend = FakeBackend({"support": None})
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == ["support"]
    home = tmp_path / "agents" / "support"
    assert yaml.safe_load((home / "agent.yaml").read_text()) == {"name": "support"}
    assert route.called


@respx.mock
def test_reconcile_stops_running_agent_missing_from_desired(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(DesiredState(node_id="node-a", agents=[]))

    assert backend.stop_calls == ["support"]
    assert route.called


@respx.mock
def test_reconcile_readopts_live_agent_without_respawn(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == []
    assert backend.stop_calls == []
    assert route.calls[0].request.content


@respx.mock
def test_reconcile_respawns_crashed_agent(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == ["support"]
    assert route.called


@respx.mock
def test_reconcile_restarts_running_agent_when_config_hash_changes(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "old-hash"}',
        encoding="utf-8",
    )
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})
    desired = _desired({"name": "support", "system_prompt": "updated"})

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert backend.stop_calls == ["support"]
    assert backend.spawn_calls == ["support"]
    hashes = (state_dir / "applied-config-hashes.json").read_text(encoding="utf-8")
    assert (
        hashlib.sha256(
            yaml.safe_dump({"name": "support", "system_prompt": "updated"}, sort_keys=True).encode()
        ).hexdigest()
        in hashes
    )
    assert route.called


@respx.mock
def test_reconcile_keeps_running_agent_when_config_hash_matches(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    desired_config = {"name": "support", "system_prompt": "same"}
    desired_hash = hashlib.sha256(
        yaml.safe_dump(desired_config, sort_keys=True).encode()
    ).hexdigest()
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump(desired_config))
    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "' + desired_hash + '"}',
        encoding="utf-8",
    )
    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": 12345})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired(desired_config))

    assert backend.stop_calls == []
    assert backend.spawn_calls == []
    assert route.called


@respx.mock
def test_reconcile_status_post_failure_does_not_raise(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.post("https://platform.internal/nodes/node-a/status").mock(
        side_effect=httpx.ConnectError("boom")
    )
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    assert backend.spawn_calls == ["support"]


@respx.mock
def test_reconcile_reports_agent_health_from_loopback_probe_and_pid_fallback(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.get("http://127.0.0.1:9101/health").mock(return_value=httpx.Response(200))
    respx.get("http://127.0.0.1:9102/health").mock(return_value=httpx.Response(503))
    status_route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(agent_id=101, name="support", config={"name": "support"}, secrets={}),
            DesiredAgent(agent_id=102, name="billing", config={"name": "billing"}, secrets={}),
            DesiredAgent(agent_id=103, name="legacy", config={"name": "legacy"}, secrets={}),
        ],
    )
    backend = FakeBackend(
        {"support": 11111, "billing": 22222, "legacy": 33333},
        gateway_ports={"support": 9101, "billing": 9102},
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert _post_body(status_route) == {
        "agents": [
            {"agent_id": 101, "phase": "running", "pid": 11111, "health": "healthy"},
            {"agent_id": 102, "phase": "running", "pid": 22222, "health": "unhealthy"},
            {"agent_id": 103, "phase": "running", "pid": 33333, "health": "healthy"},
        ]
    }


@respx.mock
def test_reconcile_marks_probe_errors_unhealthy_without_interrupting_other_agents(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    respx.get("http://127.0.0.1:9201/health").mock(side_effect=httpx.ConnectTimeout("boom"))
    respx.get("http://127.0.0.1:9202/health").mock(return_value=httpx.Response(200))
    status_route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    desired = DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(agent_id=101, name="support", config={"name": "support"}, secrets={}),
            DesiredAgent(agent_id=102, name="sales", config={"name": "sales"}, secrets={}),
        ],
    )
    backend = FakeBackend(
        {"support": 11111, "sales": 22222},
        gateway_ports={"support": 9201, "sales": 9202},
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(desired)

    assert _post_body(status_route) == {
        "agents": [
            {"agent_id": 101, "phase": "running", "pid": 11111, "health": "unhealthy"},
            {"agent_id": 102, "phase": "running", "pid": 22222, "health": "healthy"},
        ]
    }


def _agent_config_with_api_key() -> dict:
    """Minimal but valid AgentFile dict referencing ANTHROPIC_API_KEY."""
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


@respx.mock
def test_reconcile_writes_secrets_to_env_file_not_spawn(tmp_path) -> None:
    """D1: secrets are written to .env; spawn has no env param."""
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    backend = FakeBackend({"support": None})
    desired = _desired(
        config=_agent_config_with_api_key(),
        secrets={"ANTHROPIC_API_KEY": "sk-live-secret"},
    )

    reconciler = NodeReconciler(_config(tmp_path), backend)
    reconciler.reconcile(desired)

    # Secret is in .env, not injected via spawn
    env_path = tmp_path / "agents" / "support" / ".env"
    assert env_path.exists()
    env_lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert env_lines["ANTHROPIC_API_KEY"] == "sk-live-secret"
    assert oct(env_path.stat().st_mode & 0o777) == oct(0o600)

    # spawn is called without extra env arg
    assert backend.spawn_calls == ["support"]

    # On config-hash restart, secrets are written to .env again
    backend.alive["support"] = 12345
    updated_config = dict(_agent_config_with_api_key(), system_prompt="updated")
    desired_updated = _desired(
        config=updated_config,
        secrets={"ANTHROPIC_API_KEY": "sk-live-secret-v2"},
    )
    reconciler.reconcile(desired_updated)

    assert backend.stop_calls == ["support"]
    assert backend.spawn_calls == ["support", "support"]
    env_lines2 = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert env_lines2["ANTHROPIC_API_KEY"] == "sk-live-secret-v2"
    assert route.called


@respx.mock
def test_reconcile_defers_cached_start_without_secrets_but_keeps_running_agent(
    tmp_path, monkeypatch
):
    from fleetent.node import reconcile as reconcile_module
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    warnings: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            warnings.append((message, fields))

    monkeypatch.setattr(reconcile_module, "_logger", FakeLogger())

    running_backend = FakeBackend({"support": 12345})
    NodeReconciler(_config(tmp_path), running_backend).reconcile(
        _desired(secrets={}, source="cache")
    )

    waiting_backend = FakeBackend({"support": None})
    NodeReconciler(_config(tmp_path), waiting_backend).reconcile(
        _desired(secrets={}, source="cache")
    )

    assert running_backend.stop_calls == []
    assert running_backend.spawn_calls == []
    assert waiting_backend.spawn_calls == []
    assert warnings == [
        (
            "node_secret_start_deferred",
            {"agent_name": "support", "secret_env_names": [], "secret_count": 0},
        )
    ]
    assert route.called


@respx.mock
def test_write_home_creates_env_with_tui_token(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    backend = FakeBackend({"support": None})
    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(_desired())

    env_path = tmp_path / "agents" / "support" / ".env"
    assert env_path.exists()
    lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert "FLEETENT_TUI_TOKEN" in lines
    token = lines["FLEETENT_TUI_TOKEN"]
    assert token.startswith("ma-")
    assert len(token) == 67


@respx.mock
def test_write_home_preserves_existing_env_token_on_config_restart(tmp_path) -> None:
    from fleetent.node.reconcile import NodeReconciler

    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(yaml.safe_dump({"name": "support"}))
    existing_token = "ma-" + "d" * 64
    (home / ".env").write_text(f"FLEETENT_TUI_TOKEN={existing_token}\n", encoding="utf-8")

    state_dir = tmp_path / "node"
    state_dir.mkdir(parents=True)
    (state_dir / "applied-config-hashes.json").write_text(
        '{"support": "old-hash"}', encoding="utf-8"
    )

    backend = FakeBackend({"support": 12345})
    respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired({"name": "support", "version": 2})
    )

    env_content = (home / ".env").read_text(encoding="utf-8")
    assert f"FLEETENT_TUI_TOKEN={existing_token}" in env_content


@respx.mock
def test_reconcile_logs_secret_metadata_without_plaintext_on_spawn(tmp_path, monkeypatch):
    from fleetent.node import reconcile as reconcile_module
    from fleetent.node.reconcile import NodeReconciler

    route = respx.post("https://platform.internal/nodes/node-a/status").mock(
        return_value=httpx.Response(200, json={"node_id": "node-a", "updated": 1})
    )
    records: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def info(self, message: str, **fields: object) -> None:
            records.append((message, fields))

        def warn(self, message: str, **fields: object) -> None:
            pass  # reconcile may warn on config parse errors; not under test here

    monkeypatch.setattr(reconcile_module, "_logger", FakeLogger())
    backend = FakeBackend({"support": None})

    NodeReconciler(_config(tmp_path), backend).reconcile(
        _desired(secrets={"ANTHROPIC_API_KEY": "sk-live-secret"})
    )

    assert records == [
        (
            "node_agent_spawn",
            {
                "agent_name": "support",
                "secret_env_names": ["ANTHROPIC_API_KEY"],
                "secret_count": 1,
            },
        )
    ]
    assert route.called
