from __future__ import annotations

import hashlib

import httpx
import respx
import yaml

from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState


class FakeBackend:
    def __init__(self, alive: dict[str, int | None]) -> None:
        self.alive = alive
        self.spawn_calls: list[str] = []
        self.stop_calls: list[str] = []

    def spawn(self, agent_name: str) -> None:
        self.spawn_calls.append(agent_name)

    def stop(self, agent_name: str) -> None:
        self.stop_calls.append(agent_name)

    def is_alive(self, agent_name: str) -> int | None:
        return self.alive.get(agent_name)


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _desired(config: dict[str, object] | None = None) -> DesiredState:
    return DesiredState(
        node_id="node-a",
        agents=[DesiredAgent(agent_id=101, name="support", config=config or {"name": "support"})],
    )


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
    assert hashlib.sha256(
        yaml.safe_dump({"name": "support", "system_prompt": "updated"}, sort_keys=True).encode()
    ).hexdigest() in hashes
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
