from __future__ import annotations

import json

import httpx
import respx

from fleetent.node.config import NodeConfig


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


@respx.mock
def test_provider_fetches_desired_state_and_writes_cache(tmp_path) -> None:
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    route = respx.get("https://platform.internal/nodes/node-a/desired-state").mock(
        return_value=httpx.Response(
            200,
            json={
                "node_id": "node-a",
                "agents": [
                    {"agent_id": 101, "name": "support", "config": {"name": "support"}},
                    {"agent_id": 102, "name": "sales", "config": {"name": "sales"}},
                ],
            },
        )
    )

    provider = PlatformApiDesiredStateProvider(_config(tmp_path))

    desired = provider.fetch()

    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer " + "ma-" + "1" * 64
    assert [agent.agent_id for agent in desired.agents] == [101, 102]
    assert [agent.name for agent in desired.agents] == ["support", "sales"]
    cache = json.loads((tmp_path / "node" / "desired-state-cache.json").read_text())
    assert cache["node_id"] == "node-a"
    assert cache["agents"][0]["name"] == "support"


@respx.mock
def test_provider_falls_back_to_cache_when_platform_unreachable(tmp_path) -> None:
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    cache_dir = tmp_path / "node"
    cache_dir.mkdir(parents=True)
    (cache_dir / "desired-state-cache.json").write_text(
        json.dumps(
            {
                "node_id": "node-a",
                "agents": [{"agent_id": 101, "name": "support", "config": {"name": "support"}}],
            }
        )
    )
    respx.get("https://platform.internal/nodes/node-a/desired-state").mock(
        side_effect=httpx.ConnectError("boom")
    )

    provider = PlatformApiDesiredStateProvider(_config(tmp_path))

    desired = provider.fetch()

    assert [agent.name for agent in desired.agents] == ["support"]


@respx.mock
def test_provider_returns_empty_when_platform_unreachable_and_no_cache(tmp_path) -> None:
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    respx.get("https://platform.internal/nodes/node-a/desired-state").mock(
        side_effect=httpx.ConnectError("boom")
    )

    provider = PlatformApiDesiredStateProvider(_config(tmp_path))

    desired = provider.fetch()

    assert desired.node_id == "node-a"
    assert desired.agents == []
