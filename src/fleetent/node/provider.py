from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from fleetent.node.config import NodeConfig
from fleetent.structured_logging import get_logger

_logger = get_logger("node.provider")


@dataclass(frozen=True)
class DesiredSkillFile:
    path: str
    content_b64: str


@dataclass(frozen=True)
class DesiredSkill:
    name: str
    version: str
    files: list[DesiredSkillFile]


@dataclass(frozen=True)
class DesiredAgent:
    agent_id: int
    name: str
    config: dict[str, Any]
    secrets: dict[str, str]
    skills: list[DesiredSkill] = field(default_factory=list)


@dataclass(frozen=True)
class DesiredState:
    node_id: str
    agents: list[DesiredAgent]
    source: str = "remote"


class BaseDesiredStateProvider(Protocol):
    def fetch(self) -> DesiredState: ...


class PlatformApiDesiredStateProvider:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config
        self._cache_path = config.home_dir / "node" / "desired-state-cache.json"
        self._last_live_secrets_by_agent: dict[str, dict[str, str]] = {}

    def fetch(self) -> DesiredState:
        try:
            payload = self._fetch_remote()
        except httpx.HTTPError:
            cached = self._read_cache()
            if cached is None:
                return DesiredState(node_id=self._config.node_id, agents=[], source="cache")
            state = _overlay_last_live_secrets(cached, self._last_live_secrets_by_agent)
            _logger.warn(
                "node_desired_state_cache_fallback",
                agent_count=len(state.agents),
                reused_secret_env_names_by_agent=_secret_env_names_by_agent(state),
                reused_secret_count_by_agent=_secret_count_by_agent(state),
            )
            return state
        state = _desired_state_from_payload(payload, source="remote")
        self._last_live_secrets_by_agent = {
            agent.name: dict(agent.secrets) for agent in state.agents if agent.secrets
        }
        _logger.info(
            "node_desired_state_fetched",
            agent_count=len(state.agents),
            secret_env_names_by_agent=_secret_env_names_by_agent(state),
            secret_count_by_agent=_secret_count_by_agent(state),
        )
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
        return _desired_state_from_payload(
            json.loads(self._cache_path.read_text(encoding="utf-8")),
            source="cache",
        )

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(_strip_secrets_for_cache(payload), sort_keys=True),
            encoding="utf-8",
        )


def _desired_state_from_payload(payload: dict[str, Any], *, source: str) -> DesiredState:
    return DesiredState(
        node_id=str(payload["node_id"]),
        agents=[
            DesiredAgent(
                agent_id=int(agent["agent_id"]),
                name=str(agent["name"]),
                config=dict(agent["config"]),
                secrets={
                    str(key): str(value) for key, value in dict(agent.get("secrets", {})).items()
                },
                skills=_skills_from_payload(agent.get("skills", [])),
            )
            for agent in payload.get("agents", [])
        ],
        source=source,
    )


def _skills_from_payload(raw_skills: Any) -> list[DesiredSkill]:
    return [
        DesiredSkill(
            name=str(skill["name"]),
            version=str(skill["version"]),
            files=[
                DesiredSkillFile(path=str(f["path"]), content_b64=str(f["content_b64"]))
                for f in skill.get("files", [])
            ],
        )
        for skill in raw_skills
    ]


def _strip_secrets_for_cache(payload: dict[str, Any]) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    for agent in payload.get("agents", []):
        serialized = dict(agent)
        serialized.pop("secrets", None)
        agents.append(serialized)
    return {"node_id": payload["node_id"], "agents": agents}


def _overlay_last_live_secrets(
    state: DesiredState,
    last_live_secrets_by_agent: dict[str, dict[str, str]],
) -> DesiredState:
    return DesiredState(
        node_id=state.node_id,
        agents=[
            DesiredAgent(
                agent_id=agent.agent_id,
                name=agent.name,
                config=agent.config,
                secrets=dict(last_live_secrets_by_agent.get(agent.name, agent.secrets)),
                skills=agent.skills,
            )
            for agent in state.agents
        ],
        source=state.source,
    )


def _secret_env_names_by_agent(state: DesiredState) -> dict[str, list[str]]:
    return {agent.name: sorted(agent.secrets) for agent in state.agents if agent.secrets}


def _secret_count_by_agent(state: DesiredState) -> dict[str, int]:
    return {agent.name: len(agent.secrets) for agent in state.agents if agent.secrets}
