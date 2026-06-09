"""Tests for write_file (file-tools-sandbox-execution, Task 4).

Docker-unavailable in unit tests, so write_file is driven through the host backend
rooted at tmp_path; container writes (content over stdin) are covered in integration.
"""

from __future__ import annotations

import pytest

from fleetent.tools import file_tools
from fleetent.tools.file_tools import write_file


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    async def _select(tool_context):
        return file_tools._HostBackend(root=tmp_path)

    monkeypatch.setattr(file_tools, "_select_backend", _select)
    return tmp_path


async def test_write_file_creates_file(workspace):
    result = await write_file("out.txt", "hello world")
    assert (workspace / "out.txt").read_text() == "hello world"
    assert "11" in result


async def test_write_file_creates_parent_dirs(workspace):
    await write_file("nested/deep/f.txt", "x")
    assert (workspace / "nested" / "deep" / "f.txt").read_text() == "x"


async def test_write_file_overwrites(workspace):
    (workspace / "f.txt").write_text("old")
    await write_file("f.txt", "new")
    assert (workspace / "f.txt").read_text() == "new"


async def test_write_file_escape_rejected(workspace):
    result = await write_file("../escape.txt", "x")
    assert "error" in result.lower()
    assert not (workspace.parent / "escape.txt").exists()


async def test_write_file_absolute_outside_rejected(workspace):
    result = await write_file("/tmp/evil.txt", "x")
    assert "error" in result.lower()
