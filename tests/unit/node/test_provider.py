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


@respx.mock
def test_provider_parses_secrets_but_strips_them_from_disk_cache(tmp_path) -> None:
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    respx.get("https://platform.internal/nodes/node-a/desired-state").mock(
        return_value=httpx.Response(
            200,
            json={
                "node_id": "node-a",
                "agents": [
                    {
                        "agent_id": 101,
                        "name": "support",
                        "config": {"name": "support"},
                        "secrets": {"ANTHROPIC_API_KEY": "sk-live-secret"},
                    }
                ],
            },
        )
    )

    provider = PlatformApiDesiredStateProvider(_config(tmp_path))

    desired = provider.fetch()
    cache = json.loads((tmp_path / "node" / "desired-state-cache.json").read_text())
    cached = provider._read_cache()

    assert desired.agents[0].secrets == {"ANTHROPIC_API_KEY": "sk-live-secret"}
    assert "secrets" not in cache["agents"][0]
    assert cached is not None
    assert cached.agents[0].secrets == {}


@respx.mock
def test_provider_reuses_last_live_secrets_when_falling_back_to_cache(tmp_path) -> None:
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    route = respx.get("https://platform.internal/nodes/node-a/desired-state")
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "node_id": "node-a",
                "agents": [
                    {
                        "agent_id": 101,
                        "name": "support",
                        "config": {"name": "support"},
                        "secrets": {"ANTHROPIC_API_KEY": "sk-live-secret"},
                    }
                ],
            },
        )
    )
    provider = PlatformApiDesiredStateProvider(_config(tmp_path))
    first = provider.fetch()

    route.mock(side_effect=httpx.ConnectError("boom"))
    second = provider.fetch()

    assert first.source == "remote"
    assert second.source == "cache"
    assert second.agents[0].secrets == {"ANTHROPIC_API_KEY": "sk-live-secret"}


@respx.mock
def test_provider_logs_secret_metadata_without_plaintext(tmp_path, monkeypatch) -> None:
    from fleetent.node import provider as provider_module
    from fleetent.node.provider import PlatformApiDesiredStateProvider

    records: list[tuple[str, str, dict[str, object]]] = []

    class FakeLogger:
        def info(self, message: str, **fields: object) -> None:
            records.append(("info", message, fields))

        def warn(self, message: str, **fields: object) -> None:
            records.append(("warn", message, fields))

    monkeypatch.setattr(provider_module, "_logger", FakeLogger())
    route = respx.get("https://platform.internal/nodes/node-a/desired-state")
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "node_id": "node-a",
                "agents": [
                    {
                        "agent_id": 101,
                        "name": "support",
                        "config": {"name": "support"},
                        "secrets": {"ANTHROPIC_API_KEY": "sk-live-secret"},
                    }
                ],
            },
        )
    )
    provider = PlatformApiDesiredStateProvider(_config(tmp_path))

    provider.fetch()
    route.mock(side_effect=httpx.ConnectError("boom"))
    provider.fetch()

    assert records == [
        (
            "info",
            "node_desired_state_fetched",
            {
                "agent_count": 1,
                "secret_env_names_by_agent": {"support": ["ANTHROPIC_API_KEY"]},
                "secret_count_by_agent": {"support": 1},
            },
        ),
        (
            "warn",
            "node_desired_state_cache_fallback",
            {
                "agent_count": 1,
                "reused_secret_env_names_by_agent": {"support": ["ANTHROPIC_API_KEY"]},
                "reused_secret_count_by_agent": {"support": 1},
            },
        ),
    ]
