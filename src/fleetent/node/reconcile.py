from __future__ import annotations

import base64
import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import yaml

from fleetent.agent_config import AgentFile
from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredSkill, DesiredState
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
                self._remove_disappeared(name, pid, desired_state.source, hashes)
                continue

            desired_hash = _config_hash(desired.config)
            if desired_state.source == "cache" and not desired.secrets:
                if pid is None:
                    _logger.warn(
                        "node_secret_start_deferred",
                        agent_name=name,
                        secret_env_names=[],
                        secret_count=0,
                    )
                    continue
                continue
            if pid is None:
                self._write_home(desired)
                self._spawn(desired)
                hashes[name] = desired_hash
                continue

            current_hash = hashes.get(name) or self._current_home_hash(name)
            if current_hash != desired_hash or self._skills_changed(name, desired.skills):
                self._backend.stop(name)
                self._write_home(desired)
                self._spawn(desired)
                hashes[name] = desired_hash

        self._write_hashes(hashes)
        self._post_status(desired_state)

    def _spawn(self, desired: DesiredAgent) -> None:
        _logger.info(
            "node_agent_spawn",
            agent_name=desired.name,
            secret_env_names=sorted(desired.secrets),
            secret_count=len(desired.secrets),
        )
        self._backend.spawn(desired.name, env=desired.secrets)

    def _remove_disappeared(
        self, name: str, pid: int | None, source: str, hashes: dict[str, str]
    ) -> None:
        """Stop and purge an agent that vanished from the AUTHORITATIVE desired state.

        Only acts on a ``remote`` (authoritative) source. A ``cache`` fallback set may be
        stale/empty when the platform is briefly unreachable, so removals are skipped there
        to avoid stopping/deleting healthy agents.
        """
        if source != "remote":
            return
        if pid is not None:
            try:
                self._backend.stop(name)
            except Exception as exc:  # bulkhead: a failed stop must not abort reconcile
                _logger.warn("node_agent_stop_failed", agent_name=name, error=str(exc))
        self._remove_home(name)
        hashes.pop(name, None)

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

    def _write_home(self, agent: DesiredAgent) -> None:
        home = self._home_dir(agent.name)
        home.mkdir(parents=True, exist_ok=True)
        (home / "agent.yaml").write_text(
            yaml.safe_dump(agent.config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        try:
            env_names = referenced_env_names(AgentFile.model_validate(agent.config))
        except Exception:
            _logger.warn("node_write_home_config_parse_error", agent_name=agent.name)
            env_names = []
        ensure_env_scaffold(home, referenced_env_names=env_names)
        self._materialize_skills(agent.name, agent.skills)

    def _materialize_skills(self, agent_name: str, skills: list[DesiredSkill]) -> None:
        """Write node-delivered skill files under ``<home>/agents/<name>/skills/``.

        That dir is exactly what the agent process scans (``runtime/agent_app.py`` reads
        ``<home>/skills`` and ignores ``FLEETENT_SKILLS_DIR``), so no env injection is needed.
        A per-agent manifest records which skills node owns; cleanup only removes those —
        builtin copies (re-scanned from the package) and operator skills are never touched.
        """
        skills_root = self._home_dir(agent_name) / "skills"
        previous = self._read_skill_manifest(agent_name)
        valid = _valid_skills(skills, agent_name=agent_name)
        desired_names = {skill.name for skill in valid}
        # Manifest only ever holds validated single-component names, so stale paths are safe.
        for stale in set(previous) - desired_names:
            shutil.rmtree(skills_root / stale, ignore_errors=True)
        for skill in valid:
            skill_dir = skills_root / skill.name
            # Rewrite cleanly so files removed from a skill version do not linger.
            shutil.rmtree(skill_dir, ignore_errors=True)
            for file in skill.files:
                dest = skill_dir / file.path
                if not _is_within(skill_dir, dest):
                    _logger.warn(
                        "node_skill_file_path_rejected",
                        agent_name=agent_name,
                        skill=skill.name,
                        path=file.path,
                    )
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(base64.b64decode(file.content_b64))
        self._write_skill_manifest(agent_name, {skill.name: skill.version for skill in valid})

    def _skills_changed(self, agent_name: str, skills: list[DesiredSkill]) -> bool:
        desired = {skill.name: skill.version for skill in _valid_skills(skills)}
        return self._read_skill_manifest(agent_name) != desired

    def _skill_manifest_path(self, agent_name: str) -> Path:
        return self._home_dir(agent_name) / ".node-skills.json"

    def _read_skill_manifest(self, agent_name: str) -> dict[str, str]:
        path = self._skill_manifest_path(agent_name)
        if not path.exists():
            return {}
        try:
            return dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            # A corrupt manifest (e.g. truncated by a killed process) must not abort the whole
            # reconcile; treat it as missing so the next materialize rewrites it.
            _logger.warn("node_skill_manifest_unreadable", agent_name=agent_name, error=str(exc))
            return {}

    def _write_skill_manifest(self, agent_name: str, manifest: dict[str, str]) -> None:
        path = self._skill_manifest_path(agent_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    def _remove_home(self, agent_name: str) -> None:
        home = self._home_dir(agent_name)
        try:
            shutil.rmtree(home)
        except FileNotFoundError:
            return
        except OSError as exc:
            _logger.warn("node_agent_home_remove_failed", agent_name=agent_name, error=str(exc))

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


def _valid_skills(
    skills: list[DesiredSkill], *, agent_name: str | None = None
) -> list[DesiredSkill]:
    """Keep skills whose name is a safe single path component.

    Defends the on-disk skill root against a malformed/compromised desired-state payload
    (skill files are decoded from an over-the-wire bundle). Both the change detector and the
    materializer filter identically so detection converges (a rejected skill is ignored, not
    retried forever). When ``agent_name`` is given, rejections are logged once (materialize path).
    """
    valid: list[DesiredSkill] = []
    for skill in skills:
        if _is_safe_skill_name(skill.name):
            valid.append(skill)
        elif agent_name is not None:
            _logger.warn("node_skill_name_rejected", agent_name=agent_name, skill=skill.name)
    return valid


def _is_safe_skill_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def _is_within(root: Path, candidate: Path) -> bool:
    """True iff ``candidate`` is a strict descendant of ``root`` (no path traversal)."""
    return root.resolve() in candidate.resolve().parents


def _status_payload(agent_id: int, pid: int | None, health: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "phase": "running" if pid is not None else "stopped",
    }
    if pid is not None:
        payload["pid"] = pid
        payload["health"] = health
    return payload
