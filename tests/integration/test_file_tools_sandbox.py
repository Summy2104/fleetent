"""Integration tests for the file tools running in a real sandbox container.

Skipped when docker is unavailable. Each test drives a tool through a real container
backend (workspace bind-mounted from an isolated tmp dir) and asserts the workspace
boundary holds end-to-end: in-workspace IO works, out-of-workspace paths are rejected.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from fleetent import paths
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.manager import SandboxManager, Scope
from fleetent.tools import file_tools
from fleetent.tools.file_tools import edit_file, read_file, search_content, search_files, write_file


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "version"], capture_output=True).returncode == 0
    except (FileNotFoundError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="docker not available")


@pytest.fixture
def workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    monkeypatch.setattr(paths, "workspaces_dir", lambda: root)
    return root


@pytest.fixture
async def container(
    workspace_root: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[SandboxManager, str]]:
    mgr = SandboxManager(backend=SandboxClient(), scope=Scope.SESSION)
    sess = "itest-files"
    ws_id = await mgr.acquire(Scope.SESSION, sess, "bot")
    backend = file_tools._ContainerBackend(client=mgr.backend, ws_id=ws_id, session_id=sess)

    async def _select(tool_context):
        return backend

    monkeypatch.setattr(file_tools, "_select_backend", _select)
    try:
        yield mgr, sess
    finally:
        await mgr.backend.destroy_workspace(mgr.container_name(Scope.SESSION, sess, "bot"))


async def test_write_then_read_roundtrip(container, workspace_root: Path) -> None:
    written = await write_file("notes/todo.txt", "buy milk\nship code\n")
    assert "written" in written
    # Visible on the host workspace dir (bind mount works)
    host_file = workspace_root / "itest-files" / "notes" / "todo.txt"
    assert host_file.read_text() == "buy milk\nship code\n"
    # And readable back through the tool
    read = await read_file("notes/todo.txt")
    assert "buy milk" in read
    assert "ship code" in read


async def test_edit_in_container(container) -> None:
    await write_file("code.py", "def foo():\n    return 1\n")
    result = await edit_file("code.py", "return 1", "return 42")
    assert "替换成功" in result
    assert "return 42" in await read_file("code.py")


async def test_search_content_scoped_to_workspace(container) -> None:
    await write_file("a.py", "API_KEY = 'x'\n")
    await write_file("b.txt", "nothing here\n")
    result = await search_content("API_KEY", path=".")
    assert "a.py" in result
    assert "API_KEY" in result


async def test_search_files_scoped_to_workspace(container) -> None:
    await write_file("one.py", "x")
    await write_file("two.py", "y")
    await write_file("note.txt", "z")
    result = await search_files("*.py", path=".")
    assert "one.py" in result
    assert "two.py" in result
    assert "note.txt" not in result


async def test_read_outside_workspace_rejected(container) -> None:
    result = await read_file("/etc/passwd")
    assert "error" in result.lower()
    assert "root:" not in result


async def test_search_content_outside_workspace_rejected(container) -> None:
    result = await search_content("root", path="/etc")
    assert "error" in result.lower()
    assert "root:" not in result
