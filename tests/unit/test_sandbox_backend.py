"""Tests for the backend abstraction base (sandbox-backend-abstraction).

The continuity template (`exec(session_id=...)`) is backend-agnostic: it lives on
`BaseSandboxBackend` and drives a subclass's `_run_exec` primitive. A `FakeBackend`
exercises it without any real container/microVM.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fleetent.integrations.sandbox.backend import (
    BackendCapabilities,
    BaseSandboxBackend,
    ExecResult,
)
from fleetent.integrations.sandbox.session_snapshot import cwd_marker


class FakeBackend(BaseSandboxBackend):
    """Minimal backend that records `_run_exec` commands and replays scripted output."""

    name = "fake"
    capabilities = BackendCapabilities(
        persist_workspace=False, workspace_mount=False, orphan_cleanup=False
    )

    def __init__(self) -> None:
        super().__init__()
        self.commands: list[str] = []
        self._next: dict[str, ExecResult] = {}
        self.capture_exit = 0

    def script(self, substring: str, result: ExecResult) -> None:
        self._next[substring] = result

    async def available(self) -> bool:
        return True

    async def create_workspace(
        self, name, resources=None, image=None, env=None, workspace_host_path=None, config_hash=None
    ) -> str:
        return "ws-" + name

    async def find_workspace(self, name):
        return None

    async def destroy_workspace(self, workspace_id) -> None:
        return None

    async def kill_workspace(self, workspace_id) -> None:
        return None

    async def _run_exec(self, workspace_id, command, stdin=None) -> ExecResult:
        self.commands.append(command)
        if "declare -f" in command:  # unique to the capture script
            return ExecResult(stdout="", stderr="", exit_code=self.capture_exit)
        for sub, res in self._next.items():
            if sub in command:
                return res
        return ExecResult(stdout="", stderr="", exit_code=0)


def test_backend_capabilities_is_frozen_dataclass() -> None:
    caps = BackendCapabilities(persist_workspace=True, workspace_mount=True, orphan_cleanup=True)
    assert (caps.persist_workspace, caps.workspace_mount, caps.orphan_cleanup) == (
        True,
        True,
        True,
    )
    with pytest.raises(FrozenInstanceError):
        caps.persist_workspace = False  # type: ignore[misc]


async def test_exec_without_session_runs_verbatim() -> None:
    backend = FakeBackend()
    await backend.exec("ws", "echo hi")
    # No snapshot wrapping: the raw command reaches _run_exec exactly once.
    assert backend.commands == ["echo hi"]


async def test_exec_with_session_captures_then_wraps() -> None:
    backend = FakeBackend()
    marker = cwd_marker("s1")
    backend.script(
        "source ",
        ExecResult(stdout=f"out\n{marker}/workspace/sub{marker}\n", stderr="", exit_code=0),
    )
    result = await backend.exec("ws", "pwd", session_id="s1")
    # First command captures env; second is the wrapped command (sources snapshot).
    assert "export -p >" in backend.commands[0]
    assert any("source " in c for c in backend.commands[1:])
    # cwd persisted from the marker, and the marker is stripped from returned output.
    assert backend._cwd["s1"] == "/workspace/sub"
    assert marker not in result.stdout
    assert "out" in result.stdout


async def test_exec_degrades_to_login_shell_when_capture_fails() -> None:
    backend = FakeBackend()
    backend.capture_exit = 1  # capture fails -> no snapshot continuity
    await backend.exec("ws", "echo hi", session_id="s2")
    # Falls back to a login shell carrying the command; never marks snap ready.
    assert "s2" not in backend._snap_ready
    assert any("bash -lc" in c and "echo hi" not in backend.commands[0] for c in backend.commands)


async def test_capability_gated_defaults() -> None:
    """Backends that do not override the gated methods get safe defaults."""
    backend = FakeBackend()
    assert await backend.image_exists("x") is False
    assert await backend.list_workspaces("sandbox-") == []
    assert await backend.inspect_config_hash("name") is None
    with pytest.raises(NotImplementedError):
        await backend.commit_workspace("ws", "tag")
