from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol

from fleetent.node.config import NodeConfig


class BaseProcessBackend(Protocol):
    def spawn(self, agent_name: str, env: dict[str, str] | None = None) -> None: ...

    def stop(self, agent_name: str) -> None: ...

    def is_alive(self, agent_name: str) -> int | None: ...


class LocalProcessBackend:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config

    def spawn(self, agent_name: str, env: dict[str, str] | None = None) -> None:
        subprocess.Popen(
            [
                "fleetent",
                "agent",
                "run",
                agent_name,
                "--home",
                str(self._home_dir(agent_name)),
            ],
            cwd=str(self._config.home_dir),
            env={**os.environ, **(env or {})},
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

    def _home_dir(self, agent_name: str) -> Path:
        return self._config.home_dir / "agents" / agent_name
