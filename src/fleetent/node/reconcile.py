from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import yaml

from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredState


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
            if pid is None:
                self._write_home(name, desired.config)
                self._backend.spawn(name)
                hashes[name] = desired_hash
                continue

            current_hash = hashes.get(name) or self._current_home_hash(name)
            if current_hash != desired_hash:
                self._backend.stop(name)
                self._write_home(name, desired.config)
                self._backend.spawn(name)
                hashes[name] = desired_hash

        self._write_hashes(hashes)
        self._post_status(desired_state)

    def _post_status(self, desired_state: DesiredState) -> None:
        payload = {
            "agents": [
                _status_payload(agent.agent_id, self._backend.is_alive(agent.name))
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

    def _write_home(self, agent_name: str, config: dict[str, Any]) -> None:
        home = self._home_dir(agent_name)
        home.mkdir(parents=True, exist_ok=True)
        (home / "agent.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

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


def _status_payload(agent_id: int, pid: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "phase": "running" if pid is not None else "stopped",
    }
    if pid is not None:
        payload["pid"] = pid
    return payload
