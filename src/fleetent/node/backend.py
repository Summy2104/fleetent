from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Protocol

from fleetent import paths
from fleetent.db import create_substrate
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.node.config import NodeConfig
from fleetent.schema_migrations import migrate
from fleetent.tenant_router import ensure_tenant_kb_dir


class BaseProcessBackend(Protocol):
    def spawn(self, agent_name: str, tenant_id: str = "default") -> None: ...

    def stop(self, agent_name: str, tenant_id: str = "default") -> None: ...

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None: ...

    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None: ...

    def agent_endpoint(self, agent_name: str, tenant_id: str = "default") -> tuple[str, int]: ...


class LocalProcessBackend:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config
        self._gateway_ports: dict[str, int] = {}
        self._procs: dict[str, subprocess.Popen[bytes]] = {}

    def spawn(self, agent_name: str, tenant_id: str = "default") -> None:
        port = self._gateway_ports.setdefault(agent_name, self._allocate_loopback_port())
        self._procs[agent_name] = subprocess.Popen(
            [
                "fleetent",
                "agent",
                "run",
                agent_name,
                "--port",
                str(port),
                "--home",
                str(self._home_dir(agent_name, tenant_id)),
            ],
            cwd=str(self._config.home_dir),
        )

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:
        try:
            subprocess.run(
                [
                    "fleetent",
                    "agent",
                    "stop",
                    agent_name,
                    "--home",
                    str(self._home_dir(agent_name, tenant_id)),
                ],
                check=True,
            )
        finally:
            proc = self._procs.pop(agent_name, None)
            if proc is not None:
                proc.poll()

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        proc = self._procs.get(agent_name)
        if proc is not None:
            proc.poll()
            if proc.returncode is not None:
                return None

        pid_file = self._home_dir(agent_name, tenant_id) / ".fleetent.pid"
        if not pid_file.exists():
            return None
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        return pid

    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        return self._gateway_ports.get(agent_name)

    def agent_endpoint(self, agent_name: str, tenant_id: str = "default") -> tuple[str, int]:
        port = self.gateway_port(agent_name, tenant_id)
        if port is None:
            raise KeyError(agent_name)
        return ("127.0.0.1", port)

    def _home_dir(self, agent_name: str, tenant_id: str) -> Path:
        relative = paths.tenant_agent_home_dir(tenant_id, agent_name).relative_to(paths.base_dir())
        return self._config.home_dir / relative

    def _allocate_loopback_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])


class ContainerBackend:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config

    def spawn(self, agent_name: str, tenant_id: str = "default") -> None:
        home_dir = self._home_dir(agent_name, tenant_id)
        home_dir.mkdir(parents=True, exist_ok=True)
        self._prepare_tenant_kb(tenant_id)
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self._container_name(agent_name, tenant_id),
                "--label",
                "fleetent.role=agent",
                "--label",
                f"fleetent.agent.name={agent_name}",
                "--label",
                f"fleetent.agent.tenant={tenant_id}",
                "--network",
                self._config.agent_network,
                "--env-file",
                str(home_dir / ".env"),
                "--mount",
                self._bind_mount(home_dir, read_only=False),
                "--mount",
                self._bind_mount(
                    ensure_tenant_kb_dir(self._config.home_dir, tenant_id), read_only=True
                ),
                self._config.agent_image,
                "fleetent",
                "agent",
                "run",
                agent_name,
                "--port",
                str(self._config.agent_internal_port),
                "--home",
                str(home_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def stop(self, agent_name: str, tenant_id: str = "default") -> None:
        container_name = self._container_name(agent_name, tenant_id)
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    container_name,
                    "fleetent",
                    "agent",
                    "stop",
                    agent_name,
                    "--home",
                    str(self._home_dir(agent_name, tenant_id)),
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            subprocess.run(["docker", "stop", container_name], check=True)

    def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                "label=fleetent.role=agent",
                "--filter",
                f"label=fleetent.agent.name={agent_name}",
                "--filter",
                f"label=fleetent.agent.tenant={tenant_id}",
                "--filter",
                "status=running",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return 1 if result.stdout.strip() else None

    def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
        return self._config.agent_internal_port

    def agent_endpoint(self, agent_name: str, tenant_id: str = "default") -> tuple[str, int]:
        return (self._container_name(agent_name, tenant_id), self._config.agent_internal_port)

    def _tenant_dir(self, tenant_id: str) -> Path:
        relative = paths.tenant_dir(tenant_id).relative_to(paths.base_dir())
        return self._config.home_dir / relative

    def _prepare_tenant_kb(self, tenant_id: str) -> None:
        kb_dir = ensure_tenant_kb_dir(self._config.home_dir, tenant_id)
        migrate(create_substrate(f"sqlite:///{kb_dir / 'kb.db'}"), KB_MIGRATIONS)
        (kb_dir / "kb_vectors.db").touch(exist_ok=True)

    def _home_dir(self, agent_name: str, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "agents" / agent_name

    def _container_name(self, agent_name: str, tenant_id: str) -> str:
        return f"fleetent-agent-{tenant_id}-{agent_name}"

    def _bind_mount(self, path: Path, *, read_only: bool) -> str:
        readonly = "true" if read_only else "false"
        return f"type=bind,source={path},target={path},readonly={readonly}"


def create_process_backend(config: NodeConfig) -> BaseProcessBackend:
    if config.backend == "container":
        return ContainerBackend(config)
    return LocalProcessBackend(config)
