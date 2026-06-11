"""Unit tests for file-tools backend selection (file-tools-sandbox-execution, Task 2).

Sandbox available → container backend (operates inside /workspace via client.exec);
sandbox OFF (docker unavailable / mode=off) → host backend fenced to the workspace
host dir. LLM/docker are mocked; no real container is started here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fleetent.integrations.sandbox.backend import BackendCapabilities
from fleetent.integrations.sandbox.enablement import Mode
from fleetent.integrations.sandbox.manager import Scope
from fleetent.tools import file_tools


class _FakeManager:
    scope = Scope.SESSION

    def __init__(self, root, *, workspace_mount: bool = True) -> None:
        self.backend = SimpleNamespace(
            capabilities=BackendCapabilities(
                persist_workspace=True, workspace_mount=workspace_mount, orphan_cleanup=True
            )
        )
        self._root = root
        self.acquired: tuple | None = None

    async def acquire(self, scope, session_id, agent_name, env=None) -> str:
        self.acquired = (scope, session_id, agent_name)
        return "ws-abc123"

    def workspace_host_path(self, scope, session_id, agent_name):
        return self._root


@pytest.fixture
def fake_manager(tmp_path, monkeypatch):
    mgr = _FakeManager(tmp_path / "workspace")
    monkeypatch.setattr(file_tools, "_get_sandbox_manager", lambda: mgr)
    return mgr


async def test_select_host_backend_when_mount_unsupported(tmp_path, monkeypatch) -> None:
    """mode != OFF but backend lacks workspace_mount -> host fence (design D3)."""
    mgr = _FakeManager(tmp_path / "workspace", workspace_mount=False)
    monkeypatch.setattr(file_tools, "_get_sandbox_manager", lambda: mgr)

    async def _mode() -> Mode:
        return Mode.ALL

    monkeypatch.setattr(file_tools, "get_effective_mode", _mode)
    backend = await file_tools._select_backend(None)
    assert isinstance(backend, file_tools._HostBackend)
    assert backend.root == mgr._root
    assert mgr.acquired is None  # never acquired a container workspace


async def _set_mode(monkeypatch, mode: Mode) -> None:
    async def _mode() -> Mode:
        return mode

    monkeypatch.setattr(file_tools, "get_effective_mode", _mode)


async def test_select_container_backend_when_enabled(fake_manager, monkeypatch) -> None:
    await _set_mode(monkeypatch, Mode.ALL)
    backend = await file_tools._select_backend(None)
    assert isinstance(backend, file_tools._ContainerBackend)
    assert backend.ws_id == "ws-abc123"
    assert fake_manager.acquired is not None


async def test_select_host_backend_when_off(fake_manager, monkeypatch) -> None:
    await _set_mode(monkeypatch, Mode.OFF)
    backend = await file_tools._select_backend(None)
    assert isinstance(backend, file_tools._HostBackend)
    assert backend.root == fake_manager._root


async def test_container_backend_keys_on_tool_context(fake_manager, monkeypatch) -> None:
    await _set_mode(monkeypatch, Mode.ALL)
    ctx = file_tools_tool_context(session_id="sess-1", agent_name="bot")
    await file_tools._select_backend(ctx)
    scope, session_id, agent_name = fake_manager.acquired
    assert session_id == "sess-1"
    assert agent_name == "bot"


def file_tools_tool_context(session_id: str, agent_name: str):
    from fleetent.tools.registry import ToolContext

    return ToolContext(session_id=session_id, agent_name=agent_name)
