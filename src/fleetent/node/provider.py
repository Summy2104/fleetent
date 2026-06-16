from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from fleetent.node.config import NodeConfig


@dataclass(frozen=True)
class DesiredAgent:
    agent_id: int
    name: str
    config: dict[str, Any]


@dataclass(frozen=True)
class DesiredState:
    node_id: str
    agents: list[DesiredAgent]


class BaseDesiredStateProvider(Protocol):
    def fetch(self) -> DesiredState: ...


class PlatformApiDesiredStateProvider:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config
        self._cache_path = config.home_dir / "node" / "desired-state-cache.json"

    def fetch(self) -> DesiredState:
        try:
            payload = self._fetch_remote()
        except httpx.HTTPError:
            cached = self._read_cache()
            if cached is None:
                return DesiredState(node_id=self._config.node_id, agents=[])
            return cached
        state = _desired_state_from_payload(payload)
        self._write_cache(payload)
        return state

    def _fetch_remote(self) -> dict[str, Any]:
        url = f"{self._config.platform_url}/nodes/{self._config.node_id}/desired-state"
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {self._config.service_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def _read_cache(self) -> DesiredState | None:
        if not self._cache_path.exists():
            return None
        return _desired_state_from_payload(json.loads(self._cache_path.read_text(encoding="utf-8")))

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _desired_state_from_payload(payload: dict[str, Any]) -> DesiredState:
    return DesiredState(
        node_id=str(payload["node_id"]),
        agents=[
            DesiredAgent(
                agent_id=int(agent["agent_id"]),
                name=str(agent["name"]),
                config=dict(agent["config"]),
            )
            for agent in payload.get("agents", [])
        ],
    )
