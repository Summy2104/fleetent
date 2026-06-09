"""Tests for edit_file with 6-layer fallback matcher (builtin-file-tools + sandbox).

edit_file now reads the file through the workspace-fenced backend, runs the 6-layer
matcher on the host, then writes the result back through the backend. Docker is
unavailable in unit tests, so we drive the host backend rooted at tmp_path with
relative, in-workspace paths. The matching behavior is unchanged.
"""

from __future__ import annotations

import pytest

from fleetent.tools import file_tools
from fleetent.tools.file_tools import edit_file


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    async def _select(tool_context):
        return file_tools._HostBackend(root=tmp_path)

    monkeypatch.setattr(file_tools, "_select_backend", _select)
    return tmp_path


def _write(ws, name: str, content: str):
    f = ws / name
    f.write_text(content, encoding="utf-8")
    return f


# ── Layer 1: ExactReplacer ────────────────────────────────────────────────────


async def test_edit_exact_match(workspace):
    f = _write(workspace, "f.py", "def foo():\n    return 1\n")
    result = await edit_file("f.py", "return 1", "return 42")
    assert "ExactReplacer" in result
    assert f.read_text() == "def foo():\n    return 42\n"


async def test_edit_exact_not_found_all_layers_fail(workspace):
    _write(workspace, "f.py", "def foo():\n    return 1\n")
    result = await edit_file("f.py", "totally_absent_xyz", "new")
    assert "error" in result.lower()
    assert "6" in result


async def test_edit_replace_all_replaces_all_occurrences(workspace):
    f = _write(workspace, "f.py", "x = 1\ny = 1\nz = 1\n")
    result = await edit_file("f.py", "1", "2", replace_all=True)
    assert "替换成功" in result
    assert f.read_text() == "x = 2\ny = 2\nz = 2\n"


async def test_edit_replace_first_only_by_default(workspace):
    f = _write(workspace, "f.py", "a = 1\nb = 1\n")
    await edit_file("f.py", "1", "9")
    assert f.read_text() == "a = 9\nb = 1\n"


# ── no-op guard ───────────────────────────────────────────────────────────────


async def test_edit_noop_when_identical(workspace):
    f = _write(workspace, "f.py", "hello\n")
    result = await edit_file("f.py", "hello", "hello")
    assert "no-op" in result.lower()
    assert f.read_text() == "hello\n"


# ── Layer 2: LineTrimmedReplacer ─────────────────────────────────────────────


async def test_edit_layer2_trailing_whitespace_mismatch(workspace):
    f = _write(workspace, "f.py", "def foo():\n    return 1\n")
    result = await edit_file("f.py", "def foo():\n    return 1   ", "def foo():\n    return 99")
    assert "替换成功" in result
    assert "return 99" in f.read_text()


# ── Layer 3: WhitespaceNormalizedReplacer ─────────────────────────────────────


async def test_edit_layer3_extra_spaces(workspace):
    f = _write(workspace, "f.py", "x  =  1\n")
    result = await edit_file("f.py", "x = 1", "x = 2")
    assert "替换成功" in result
    assert "2" in f.read_text()


# ── Layer 4: LineEndingNormalizedReplacer ─────────────────────────────────────


async def test_edit_layer4_crlf_in_file(workspace):
    f = _write(workspace, "f.txt", "line1\r\nline2\r\n")
    result = await edit_file("f.txt", "line1\nline2\n", "NEW\n")
    assert "替换成功" in result
    assert "NEW" in f.read_text()


# ── Layer 5: IndentationFlexibleReplacer ─────────────────────────────────────


async def test_edit_layer5_different_indentation(workspace):
    _write(workspace, "f.py", "class A:\n    def method(self):\n        pass\n")
    result = await edit_file(
        "f.py", "def method(self):\n    pass", "def method(self):\n    return 1"
    )
    assert "替换成功" in result


# ── Layer 6: ContextAwareReplacer ────────────────────────────────────────────


async def test_edit_layer6_context_anchor(workspace):
    f = _write(workspace, "f.py", "def foo():\n    x = 1\n    y = 2\n    return x + y\n")
    result = await edit_file(
        "f.py", "def foo():\nx = 1\ny = 2\nreturn x + y", "def bar():\n    return 3"
    )
    assert "替换成功" in result
    assert "bar" in f.read_text()


# ── missing file / boundary ──────────────────────────────────────────────────


async def test_edit_missing_file_returns_error(workspace):
    result = await edit_file("nope.py", "old", "new")
    assert "error" in result.lower()


async def test_edit_escape_rejected(workspace):
    result = await edit_file("../escape.py", "old", "new")
    assert "error" in result.lower()
