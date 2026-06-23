from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import yaml

from fleetent.agent_config import AgentFile
from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredState
from fleetent.runtime.agent_init import ensure_env_scaffold, referenced_env_names
from fleetent.structured_logging import get_logger

_logger = get_logger("node.reconcile")


class NodeReconciler:
    def __init__(self, config: NodeConfig, backend: BaseProcessBackend) -> None:
        self._config = config
        self._backend = backend
        self._hash_path = config.home_dir / "node" / "applied-config-hashes.json"

    def reconcile(self, desired_state: DesiredState) -> None:
        desired_by_name = {agent.name: agent for agent in desired_state.agents}
        known_names = set(desired_by_name) | set(self._local_agent_names())
        hashes = self._read_hashes()

        for name in sorted(known_names):
            desired = desired_by_name.get(name)
            pid = self._backend.is_alive(name)
            if desired is None:
                if pid is not None:
                    self._backend.stop(name)
                continue

            desired_hash = _config_hash(desired.config)
            if desired_state.source == "cache" and not desired.secrets:
                if pid is None:
                    if not self._env_has_values(name):
                        _logger.warn(
                            "node_secret_start_deferred",
                            agent_name=name,
                            secret_env_names=[],
                            secret_count=0,
                        )
                        continue
                    # .env has values from prior materialization — boot from disk
                else:
                    continue
            if pid is None:
                self._write_home(name, desired.config, secrets=desired.secrets)
                _logger.info(
                    "node_agent_spawn",
                    agent_name=name,
                    secret_env_names=sorted(desired.secrets),
                    secret_count=len(desired.secrets),
                )
                self._backend.spawn(name)
                hashes[name] = desired_hash
                continue

            current_hash = hashes.get(name) or self._current_home_hash(name)
            if current_hash != desired_hash:
                self._backend.stop(name)
                self._write_home(name, desired.config, secrets=desired.secrets)
                _logger.info(
                    "node_agent_spawn",
                    agent_name=name,
                    secret_env_names=sorted(desired.secrets),
                    secret_count=len(desired.secrets),
                )
                self._backend.spawn(name)
                hashes[name] = desired_hash

        self._write_hashes(hashes)
        self._post_status(desired_state)

    def _post_status(self, desired_state: DesiredState) -> None:
        payload = {
            "agents": [
                _status_payload(
                    agent.agent_id,
                    self._backend.is_alive(agent.name),
                    self._agent_health(agent.name),
                )
                for agent in desired_state.agents
            ]
        }
        try:
            response = httpx.post(
                f"{self._config.platform_url}/nodes/{self._config.node_id}/status",
                headers={"Authorization": f"Bearer {self._config.service_key}"},
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return

    def _agent_health(self, agent_name: str) -> str | None:
        pid = self._backend.is_alive(agent_name)
        if pid is None:
            return None

        port = self._backend.gateway_port(agent_name)
        if port is None:
            return "healthy"

        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
        except Exception:
            return "unhealthy"
        return "healthy" if response.status_code == 200 else "unhealthy"

    def _write_home(
        self, agent_name: str, config: dict[str, Any], *, secrets: dict[str, str] | None = None
    ) -> None:
        home = self._home_dir(agent_name)
        home.mkdir(parents=True, exist_ok=True)
        (home / "agent.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        try:
            env_names = referenced_env_names(AgentFile.model_validate(config))
        except Exception:
            _logger.warn("node_write_home_config_parse_error", agent_name=agent_name)
            env_names = []
        ensure_env_scaffold(home, referenced_env_names=env_names, secrets=secrets)

    def _env_has_values(self, agent_name: str) -> bool:
        """Return True if the agent's .env has at least one non-empty, non-TUI-token value."""
        env_path = self._home_dir(agent_name) / ".env"
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            if key.strip() != "FLEETENT_TUI_TOKEN" and value.strip():
                return True
        return False

    def _home_dir(self, agent_name: str) -> Path:
        return self._config.home_dir / "agents" / agent_name

    def _local_agent_names(self) -> list[str]:
        agents_dir = self._config.home_dir / "agents"
        if not agents_dir.exists():
            return []
        return [path.name for path in agents_dir.iterdir() if path.is_dir()]

    def _read_hashes(self) -> dict[str, str]:
        if not self._hash_path.exists():
            return {}
        return dict(json.loads(self._hash_path.read_text(encoding="utf-8")))

    def _current_home_hash(self, agent_name: str) -> str | None:
        agent_file = self._home_dir(agent_name) / "agent.yaml"
        if not agent_file.exists():
            return None
        return _config_hash(dict(yaml.safe_load(agent_file.read_text(encoding="utf-8")) or {}))

    def _write_hashes(self, hashes: dict[str, str]) -> None:
        self._hash_path.parent.mkdir(parents=True, exist_ok=True)
        self._hash_path.write_text(json.dumps(hashes, sort_keys=True), encoding="utf-8")


def _config_hash(config: dict[str, Any]) -> str:
    return sha256(yaml.safe_dump(config, sort_keys=True).encode("utf-8")).hexdigest()


def _status_payload(agent_id: int, pid: int | None, health: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "phase": "running" if pid is not None else "stopped",
    }
    if pid is not None:
        payload["pid"] = pid
        payload["health"] = health
    return payload
