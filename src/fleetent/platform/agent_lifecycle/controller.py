"""Start/stop controller for agent runtime processes (no monitoring).

The platform can start an agent by spawning ``fleetent agent run <name>`` and stop it by
terminating that tracked process. It tracks started PIDs only to stop them; it does NOT
health-check, restart, or supervise — a process that exits stays down until started
again (the user-chosen lightweight control model; see ``platform-agent-lifecycle``).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Protocol

from fleetent.structured_logging import get_logger

_logger = get_logger("agent_lifecycle.controller")


class _Proc(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


def _build_command(name: str) -> list[str]:
    """Argv for the agent runtime: ``python -m fleetent agent run <name>``.

    Uses the current interpreter's ``-m fleetent`` so the spawn works without relying on
    the ``fleetent`` console script being on PATH.
    """
    return [sys.executable, "-m", "fleetent", "agent", "run", name]


def _default_spawn(name: str) -> _Proc:
    return subprocess.Popen(_build_command(name))  # noqa: S603 — argv is fixed, no shell


class AgentController:
    """Spawns/terminates ``fleetent agent run`` processes; in-memory PID tracking only."""

    def __init__(self, spawn: Callable[[str], _Proc] | None = None) -> None:
        self._spawn = spawn or _default_spawn
        self._procs: dict[str, _Proc] = {}

    def start(self, name: str) -> int:
        """Spawn the agent runtime and record its process. Returns the PID."""
        existing = self._procs.get(name)
        if existing is not None and existing.poll() is None:
            _logger.warn("agent_already_running", name=name, existing_pid=existing.pid)
        proc = self._spawn(name)
        self._procs[name] = proc
        _logger.info("agent_started", name=name, pid=proc.pid)
        return proc.pid

    def stop(self, name: str) -> bool:
        """Terminate the tracked process. Returns False if nothing was tracked."""
        proc = self._procs.pop(name, None)
        if proc is None:
            _logger.warn("agent_stop_not_tracked", name=name)
            return False
        if proc.poll() is None:
            proc.terminate()
        _logger.info("agent_stopped", name=name, pid=proc.pid)
        return True

    def is_running(self, name: str) -> bool:
        """Shallow status: a tracked process whose poll() is still None. No probe."""
        proc = self._procs.get(name)
        return proc is not None and proc.poll() is None
