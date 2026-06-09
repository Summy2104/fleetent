"""Tests for read_file (builtin-file-tools + file-tools-sandbox-execution).

read_file now runs against a workspace-fenced backend. Docker is unavailable in unit
tests, so we drive the host backend rooted at ``tmp_path`` (the same fence used in the
docker-unavailable degrade) and call the tool with relative, in-workspace paths. The
functional contract — pagination, line numbers, directory listing, binary detection —
is unchanged; only the path model is narrowed to the workspace.
"""

from __future__ import annotations

import pytest

from fleetent.tools import file_tools
from fleetent.tools.file_tools import read_file


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    """Route read_file through a host backend fenced to tmp_path."""

    async def _select(tool_context):
        return file_tools._HostBackend(root=tmp_path)

    monkeypatch.setattr(file_tools, "_select_backend", _select)
    return tmp_path


# ── pagination ────────────────────────────────────────────────────────────────


async def test_read_file_default_returns_first_200_lines(workspace):
    (workspace / "big.txt").write_text("\n".join(f"line {i}" for i in range(500)) + "\n")
    result = await read_file("big.txt")
    assert "line 0" in result
    assert "line 199" in result
    assert "line 200" not in result


async def test_read_file_offset_starts_at_correct_line(workspace):
    (workspace / "f.txt").write_text("\n".join(f"L{i}" for i in range(50)) + "\n")
    result = await read_file("f.txt", offset=11, limit=5)
    assert "L10" in result
    assert "L9 " not in result
    assert "L15" not in result


async def test_read_file_limit_caps_lines(workspace):
    (workspace / "f.txt").write_text("\n".join(f"row{i}" for i in range(100)) + "\n")
    result = await read_file("f.txt", offset=1, limit=10)
    assert "row0" in result
    assert "row9" in result
    assert "row10" not in result


async def test_read_file_last_page_no_hint(workspace):
    (workspace / "short.txt").write_text("a\nb\nc\n")
    result = await read_file("short.txt", offset=1, limit=200)
    assert "offset" not in result


async def test_read_file_middle_page_has_hint(workspace):
    (workspace / "big.txt").write_text("\n".join(f"L{i}" for i in range(500)) + "\n")
    result = await read_file("big.txt", offset=1, limit=50)
    assert "offset" in result
    assert "read_file" in result


async def test_read_file_shows_line_numbers(workspace):
    (workspace / "ln.txt").write_text("alpha\nbeta\ngamma\n")
    result = await read_file("ln.txt", offset=1, limit=3)
    assert "1" in result
    assert "alpha" in result


# ── directory listing ─────────────────────────────────────────────────────────


async def test_read_file_directory_returns_listing(workspace):
    (workspace / "a.py").write_text("x")
    (workspace / "b.txt").write_text("y")
    result = await read_file(".")
    assert "a.py" in result
    assert "b.txt" in result


async def test_read_file_directory_shows_sizes(workspace):
    (workspace / "f.txt").write_text("hello world")
    result = await read_file(".")
    assert "f.txt" in result
    assert any(c.isdigit() for c in result)


async def test_read_file_directory_truncates_many_entries(workspace):
    for i in range(250):
        (workspace / f"file_{i:04d}.txt").write_text("x")
    result = await read_file(".")
    assert "截断" in result or "truncat" in result.lower()


# ── binary detection ─────────────────────────────────────────────────────────


async def test_read_file_png_magic_bytes_detected(workspace):
    (workspace / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    result = await read_file("img.png")
    assert "error" in result.lower() or "二进制" in result
    assert "png" in result.lower() or "image" in result.lower()


async def test_read_file_high_non_printable_ratio_detected(workspace):
    content = bytes([0x00, 0x01, 0x02, 0x03] * 100) + b"A" * 200
    (workspace / "binary.bin").write_bytes(content)
    result = await read_file("binary.bin")
    assert "error" in result.lower() or "二进制" in result


async def test_read_file_text_file_not_binary(workspace):
    (workspace / "code.py").write_text("def hello():\n    return 'world'\n")
    result = await read_file("code.py")
    assert "def hello" in result
    assert "error" not in result.lower()


# ── error / boundary cases ─────────────────────────────────────────────────────


async def test_read_file_missing_file_returns_error(workspace):
    result = await read_file("no_such_file.txt")
    assert "error" in result.lower()


async def test_read_file_escape_rejected(workspace):
    result = await read_file("../etc/passwd")
    assert "error" in result.lower()


async def test_read_file_absolute_outside_rejected(workspace):
    result = await read_file("/etc/passwd")
    assert "error" in result.lower()
