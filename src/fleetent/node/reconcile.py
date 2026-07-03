from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import ValidationError

from fleetent.agent_config import AgentFile
from fleetent.knowledge_base.service_config import load_host_service_config
from fleetent.node.backend import BaseProcessBackend
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredState
from fleetent.node.skill_deployer import NodeSkillDeployer
from fleetent.runtime.agent_init import ensure_env_scaffold, referenced_env_names
from fleetent.structured_logging import get_logger

_logger = get_logger("node.reconcile")
_KB_SERVICE_KEY_ENV = "FLEETENT_KB_SERVICE_KEY"


class NodeReconciler:
    def __init__(self, config: NodeConfig, backend: BaseProcessBackend) -> None:
        self._config = config
        self._backend = backend
        self._hash_path = config.home_dir / "node" / "applied-config-hashes.json"
        self._knowledge_epoch_path = (
            config.home_dir / "node" / "applied-knowledge-resync-epochs.json"
        )
        self._skill_deployer = NodeSkillDeployer(config)

    def reconcile(self, desired_state: DesiredState) -> None:
        desired_by_name = {agent.name: agent for agent in desired_state.agents}
        known_names = set(desired_by_name) | set(self._local_agent_names())
        hashes = self._read_hashes()
        knowledge_epochs = self._read_knowledge_epochs()

        for name in sorted(known_names):
            desired = desired_by_name.get(name)
            tenant_id = desired.tenant_id if desired is not None else self._local_tenant_id(name)
            pid = self._backend.is_alive(name, tenant_id)
            if desired is None:
                if pid is not None:
                    self._backend.stop(name, tenant_id)
                _erase_env(self._home_dir(name, tenant_id) / ".env")
                hashes.pop(name, None)
                knowledge_epochs.pop(name, None)
                continue

            desired_hash = _config_hash(desired.config)
            if desired_state.source == "cache" and not desired.secrets:
                if pid is not None:
                    # Already running with no fresh secrets — leave it be.
                    continue
                if not self._env_has_values(name, desired.tenant_id):
                    _logger.warn(
                        "node_secret_start_deferred",
                        agent_name=name,
                        secret_env_names=[],
                        secret_count=0,
                    )
                    continue
                # .env has values from prior materialization — boot from disk WITHOUT
                # rewriting it. We hold no authoritative secrets here, so calling
                # _write_home() would scaffold every referenced env name with an empty
                # value and blank the good on-disk credentials. Spawn from the .env as-is.
                _logger.info("node_agent_spawn_from_disk", agent_name=name)
                self._backend.spawn(name, desired.tenant_id)
                hashes[name] = desired_hash
                knowledge_epochs[name] = desired.knowledge_resync_epoch
                continue

            if pid is None:
                self._write_home(
                    name,
                    desired.tenant_id,
                    desired.config,
                    skill_manifests=desired.skill_manifests,
                    secrets=desired.secrets,
                )
                _logger.info(
                    "node_agent_spawn",
                    agent_name=name,
                    secret_env_names=sorted(desired.secrets),
                    secret_count=len(desired.secrets),
                )
                self._backend.spawn(name, desired.tenant_id)
                hashes[name] = desired_hash
                knowledge_epochs[name] = desired.knowledge_resync_epoch
                continue

            current_hash = hashes.get(name) or self._current_home_hash(name, desired.tenant_id)
            if current_hash != desired_hash:
                self._backend.stop(name, desired.tenant_id)
                self._write_home(
                    name,
                    desired.tenant_id,
                    desired.config,
                    skill_manifests=desired.skill_manifests,
                    secrets=desired.secrets,
                )
                _logger.info(
                    "node_agent_spawn",
                    agent_name=name,
                    secret_env_names=sorted(desired.secrets),
                    secret_count=len(desired.secrets),
                )
                self._backend.spawn(name, desired.tenant_id)
                hashes[name] = desired_hash
                knowledge_epochs[name] = desired.knowledge_resync_epoch
            elif knowledge_epochs.get(name, "") != desired.knowledge_resync_epoch:
                self._write_home(
                    name,
                    desired.tenant_id,
                    desired.config,
                    skill_manifests=desired.skill_manifests,
                    secrets=desired.secrets,
                )
                hashes[name] = desired_hash
                knowledge_epochs[name] = desired.knowledge_resync_epoch
            elif desired_state.source == "remote" and not self._env_has_secret_values(
                name, desired.tenant_id, desired.secrets, desired.config
            ):
                # Self-heal a blanked .env: the platform is reachable and returned real
                # secrets, but the on-disk .env is missing them (e.g. a prior restart-race
                # blanked it). Config-hash is unchanged, so no respawn would otherwise fire
                # and the agent would run with empty credentials forever. The agent reads
                # its env at process start, so we must rewrite AND respawn.
                self._backend.stop(name, desired.tenant_id)
                self._write_home(
                    name,
                    desired.tenant_id,
                    desired.config,
                    skill_manifests=desired.skill_manifests,
                    secrets=desired.secrets,
                )
                _logger.info(
                    "node_agent_env_self_heal",
                    agent_name=name,
                    secret_env_names=sorted(desired.secrets),
                    secret_count=len(desired.secrets),
                )
                self._backend.spawn(name, desired.tenant_id)
                hashes[name] = desired_hash
                knowledge_epochs[name] = desired.knowledge_resync_epoch
            else:
                # Running with unchanged config: still reconcile skills every tick so new
                # pool versions and post-backflow forced resyncs (resync_epoch) are applied
                # without waiting for a respawn — otherwise an accepted/rejected drift never
                # clears on the node and re-nomination loops forever.
                self._sync_skills(name, desired.tenant_id, desired.skill_manifests)

        self._write_hashes(hashes)
        self._write_knowledge_epochs(knowledge_epochs)
        self._post_status(desired_state)

    def _post_status(self, desired_state: DesiredState) -> None:
        payload: dict[str, object] = {
            "agents": [
                _status_payload(
                    agent.agent_id,
                    self._backend.is_alive(agent.name, agent.tenant_id),
                    self._agent_health(agent.name, agent.tenant_id),
                    self._observe_skills(agent.name, agent.tenant_id, agent.skill_manifests),
                )
                for agent in desired_state.agents
            ]
        }
        if self._config.advertise_host:
            payload["forward_host"] = self._config.advertise_host
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

    def _agent_health(self, agent_name: str, tenant_id: str) -> str | None:
        pid = self._backend.is_alive(agent_name, tenant_id)
        if pid is None:
            return None

        port = self._backend.gateway_port(agent_name, tenant_id)
        if port is None:
            return "healthy"

        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
        except Exception:
            return "unhealthy"
        return "healthy" if response.status_code == 200 else "unhealthy"

    def _write_home(
        self,
        agent_name: str,
        tenant_id: str,
        config: dict[str, Any],
        *,
        skill_manifests: list[dict[str, str]] | None = None,
        secrets: dict[str, str] | None = None,
    ) -> None:
        home = self._home_dir(agent_name, tenant_id)
        home.mkdir(parents=True, exist_ok=True)
        config, knowledge_secrets = _inject_managed_knowledge_provider(
            config,
            home_dir=self._config.home_dir,
        )
        (home / "agent.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        try:
            env_names = referenced_env_names(AgentFile.model_validate(config))
        except Exception:
            _logger.warn("node_write_home_config_parse_error", agent_name=agent_name)
            env_names = []
        # Managed signal + per-user OAuth broker address: written into the agent .env (the
        # env-only contract; the process backend never injects env=). Its presence tells the
        # agent to source per-user MCP tokens via the node loopback (mcp-per-user-oauth2-managed).
        from fleetent.node.forwarder_contract import DEFAULT_FORWARDER_PORT

        loopback_env = {"FLEETENT_NODE_LOOPBACK_URL": f"http://127.0.0.1:{DEFAULT_FORWARDER_PORT}"}
        # Public base for per-user link forms/callbacks (mcp-per-user-apikey / oauth): under
        # managed placement the credential form + OAuth callback are served by the platform, so
        # the link the agent builds must point at the platform's browser-reachable URL. Node env
        # ``FLEETENT_OAUTH_REDIRECT_BASE`` overrides (real public host); else the platform URL.
        redirect_base = (
            os.environ.get("FLEETENT_OAUTH_REDIRECT_BASE", "").strip() or self._config.platform_url
        )
        if redirect_base:
            loopback_env["FLEETENT_OAUTH_REDIRECT_BASE"] = redirect_base
        ensure_env_scaffold(
            home,
            referenced_env_names=[
                *env_names,
                "FLEETENT_NODE_LOOPBACK_URL",
                "FLEETENT_OAUTH_REDIRECT_BASE",
            ],
            secrets={**(secrets or {}), **knowledge_secrets, **loopback_env},
        )
        self._sync_skills(agent_name, tenant_id, skill_manifests)

    def _sync_skills(
        self,
        agent_name: str,
        tenant_id: str,
        skill_manifests: list[dict[str, str]] | None,
    ) -> None:
        """Bulkheaded skill deploy; a bad bundle is logged, never aborts reconcile."""
        if not skill_manifests:
            return
        home = self._home_dir(agent_name, tenant_id)
        try:
            self._skill_deployer.sync(home, skill_manifests)
        except Exception as exc:
            _logger.warn(
                "node_skill_deploy_failed",
                agent_name=agent_name,
                exception=exc,
            )

    def _env_has_values(self, agent_name: str, tenant_id: str) -> bool:
        """Return True if the agent's .env has at least one non-empty, non-TUI-token value."""
        env_path = self._home_dir(agent_name, tenant_id) / ".env"
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            if key.strip() != "FLEETENT_TUI_TOKEN" and value.strip():
                return True
        return False

    def _env_has_secret_values(
        self, agent_name: str, tenant_id: str, secrets: dict[str, str], config: dict[str, Any]
    ) -> bool:
        """Return True if the on-disk .env carries every required authoritative secret.

        A secret is required only when it is both non-empty AND referenced by the agent
        config, because the scaffold (``ensure_env_scaffold``) only ever writes referenced
        env names. Requiring an orphan secret — one whose env name no config field
        references — would loop stop → rewrite → respawn forever, since the scaffold never
        materializes it. Restricting to referenced names keeps this gate aligned with the
        scaffold and preserves the blanked-.env self-heal for real credentials. Operator
        -blank secrets are likewise excluded so clearing a value never respawns endlessly.
        """
        try:
            referenced = set(referenced_env_names(AgentFile.model_validate(config)))
        except Exception:
            # Config unparsable → the scaffold writes no referenced names either, so nothing
            # is required on disk; never self-heal into an unwinnable loop.
            referenced = set()
        required = [name for name, value in secrets.items() if value and name in referenced]
        if not required:
            return True
        env_path = self._home_dir(agent_name, tenant_id) / ".env"
        if not env_path.exists():
            return False
        on_disk: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            on_disk[key.strip()] = value.strip()
        return all(on_disk.get(name) for name in required)

    def _home_dir(self, agent_name: str, tenant_id: str) -> Path:
        return self._config.home_dir / "tenants" / tenant_id / "agents" / agent_name

    def _local_agent_names(self) -> list[str]:
        tenants_dir = self._config.home_dir / "tenants"
        if not tenants_dir.exists():
            return []
        names: list[str] = []
        for tenant_dir in tenants_dir.iterdir():
            agents_dir = tenant_dir / "agents"
            if not agents_dir.exists():
                continue
            names.extend(path.name for path in agents_dir.iterdir() if path.is_dir())
        return names

    def _local_tenant_id(self, agent_name: str) -> str:
        tenants_dir = self._config.home_dir / "tenants"
        if not tenants_dir.exists():
            return "default"
        for tenant_dir in tenants_dir.iterdir():
            if (tenant_dir / "agents" / agent_name).is_dir():
                return tenant_dir.name
        return "default"

    def _read_hashes(self) -> dict[str, str]:
        if not self._hash_path.exists():
            return {}
        return dict(json.loads(self._hash_path.read_text(encoding="utf-8")))

    def _current_home_hash(self, agent_name: str, tenant_id: str) -> str | None:
        agent_file = self._home_dir(agent_name, tenant_id) / "agent.yaml"
        if not agent_file.exists():
            return None
        return _config_hash(dict(yaml.safe_load(agent_file.read_text(encoding="utf-8")) or {}))

    def _write_hashes(self, hashes: dict[str, str]) -> None:
        self._hash_path.parent.mkdir(parents=True, exist_ok=True)
        self._hash_path.write_text(json.dumps(hashes, sort_keys=True), encoding="utf-8")

    def _read_knowledge_epochs(self) -> dict[str, str]:
        if not self._knowledge_epoch_path.exists():
            return {}
        return dict(json.loads(self._knowledge_epoch_path.read_text(encoding="utf-8")))

    def _write_knowledge_epochs(self, knowledge_epochs: dict[str, str]) -> None:
        self._knowledge_epoch_path.parent.mkdir(parents=True, exist_ok=True)
        self._knowledge_epoch_path.write_text(
            json.dumps(knowledge_epochs, sort_keys=True), encoding="utf-8"
        )

    def _observe_skills(
        self,
        agent_name: str,
        tenant_id: str,
        manifests: list[dict[str, str]],
    ) -> list[dict[str, str | bool]]:
        observe = getattr(self._skill_deployer, "observe", None)
        if observe is None:
            return []
        return observe(self._home_dir(agent_name, tenant_id), manifests)


def _erase_env(env_path: Path) -> None:
    """Bulkheaded erase of an agent's .env after it is stopped."""
    try:
        env_path.unlink(missing_ok=True)
    except OSError:
        _logger.warn("node_agent_env_wipe_failed", path=str(env_path))


def _inject_managed_knowledge_provider(
    config: dict[str, Any],
    *,
    home_dir: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    knowledge = config.get("knowledge")
    if not isinstance(knowledge, dict):
        return config, {}
    if not knowledge.get("enabled"):
        return config, {}
    bindings = knowledge.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        return config, {}
    provider = knowledge.get("provider")
    if isinstance(provider, dict) and provider.get("type") == "http":
        return config, {}

    kb_config_path = home_dir / "kb-service.yaml"
    if not kb_config_path.exists():
        return config, {}
    try:
        host_config = load_host_service_config(kb_config_path)
    except (OSError, ValidationError, ValueError):
        _logger.warn("node_kb_host_config_unavailable", path=str(kb_config_path))
        return config, {}

    auth_ref, secret_values = _managed_kb_auth_ref(host_config.service.service_key_ref)
    materialized = dict(config)
    materialized_knowledge = dict(knowledge)
    materialized_knowledge["provider"] = {
        "type": "http",
        "url": _managed_kb_url(
            host=host_config.service.host,
            port=host_config.service.port,
        ),
        "auth_ref": auth_ref,
    }
    materialized["knowledge"] = materialized_knowledge
    return materialized, secret_values


def _managed_kb_auth_ref(service_key_ref: str) -> tuple[str, dict[str, str]]:
    if service_key_ref.startswith("env:"):
        env_name = service_key_ref.removeprefix("env:")
        value = os.environ.get(env_name, "")
        if not value:
            raise ValueError(f"missing kb service key env var: {env_name}")
        return service_key_ref, {env_name: value}
    path = Path(service_key_ref.removeprefix("file://")).expanduser()
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"empty kb service key file: {path}")
    return f"env:{_KB_SERVICE_KEY_ENV}", {_KB_SERVICE_KEY_ENV: value}


def _managed_kb_url(*, host: str, port: int) -> str:
    dial_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    return f"http://{dial_host}:{port}/search"


def _config_hash(config: dict[str, Any]) -> str:
    return sha256(
        yaml.safe_dump(_runtime_config(config), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(config)
    knowledge = runtime.get("knowledge")
    if isinstance(knowledge, dict):
        normalized = dict(knowledge)
        normalized.pop("bindings", None)
        normalized.pop("enabled", None)
        if normalized:
            runtime["knowledge"] = normalized
        else:
            runtime.pop("knowledge", None)
    return runtime


def _status_payload(
    agent_id: int,
    pid: int | None,
    health: str | None,
    skills: list[dict[str, str | bool]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "phase": "running" if pid is not None else "stopped",
    }
    if pid is not None:
        payload["pid"] = pid
        payload["health"] = health
    if skills:
        payload["skills"] = skills
    return payload
