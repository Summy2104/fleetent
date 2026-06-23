from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Protocol

from fleetent.node.config import NodeConfig


class BaseProcessBackend(Protocol):
    def spawn(self, agent_name: str) -> None: ...

    def stop(self, agent_name: str) -> None: ...

    def is_alive(self, agent_name: str) -> int | None: ...

    def gateway_port(self, agent_name: str) -> int | None: ...


class LocalProcessBackend:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config
        self._gateway_ports: dict[str, int] = {}

    def spawn(self, agent_name: str) -> None:
        port = self._gateway_ports.setdefault(agent_name, self._allocate_loopback_port())
        subprocess.Popen(
            [
                "fleetent",
                "agent",
                "run",
                agent_name,
                "--no-im",
                "--port",
                str(port),
                "--home",
                str(self._home_dir(agent_name)),
            ],
            cwd=str(self._config.home_dir),
        )

    def stop(self, agent_name: str) -> None:
        subprocess.run(
            [
                "fleetent",
                "agent",
                "stop",
                agent_name,
                "--home",
                str(self._home_dir(agent_name)),
            ],
            check=True,
        )

    def is_alive(self, agent_name: str) -> int | None:
        pid_file = self._home_dir(agent_name) / ".fleetent.pid"
        if not pid_file.exists():
            return None
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        return pid

    def gateway_port(self, agent_name: str) -> int | None:
        return self._gateway_ports.get(agent_name)

    def _home_dir(self, agent_name: str) -> Path:
        return self._config.home_dir / "agents" / agent_name

    def _allocate_loopback_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])
