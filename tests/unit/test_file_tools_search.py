"""Tests for search_content and search_files (builtin-file-tools + sandbox).

Search now runs against the workspace-fenced backend. Docker is unavailable in unit
tests, so we drive the host backend rooted at tmp_path; an absolute path equal to the
root resolves to the root, so the existing tree fixtures still apply. The rg/python
fallback search logic is unchanged; only the path model is narrowed to the workspace.
"""

from __future__ import annotations

import pytest

from fleetent.tools import file_tools
from fleetent.tools.file_tools import search_content, search_files


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    async def _select(tool_context):
        return file_tools._HostBackend(root=tmp_path)

    monkeypatch.setattr(file_tools, "_select_backend", _select)
    return tmp_path


def _make_tree(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    (tmp_path / "b.py").write_text("import os\ndef baz():\n    return os.getcwd()\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("hello world\nfoo bar\n")
    (tmp_path / "sub" / "d.py").write_text("x = 42\n")
    return tmp_path


# ── search_content ────────────────────────────────────────────────────────────


async def test_search_content_finds_pattern(workspace):
    _make_tree(workspace)
    result = await search_content("def foo", path=".")
    assert "a.py" in result
    assert "def foo" in result


async def test_search_content_format_file_line_content(workspace):
    _make_tree(workspace)
    result = await search_content("return 1", path=".")
    assert ":" in result
    assert "return 1" in result


async def test_search_content_respects_include_filter(workspace):
    _make_tree(workspace)
    result = await search_content("foo", path=".", include="*.py")
    assert "c.txt" not in result


async def test_search_content_max_results_truncation(workspace):
    root = workspace / "many"
    root.mkdir()
    for i in range(20):
        (root / f"f{i}.py").write_text("\n".join(f"match_{j}" for j in range(10)) + "\n")
    result = await search_content("match_", path="many", max_results=5)
    assert "截断" in result or "5" in result


async def test_search_content_no_match_returns_no_results(workspace):
    _make_tree(workspace)
    result = await search_content("XYZNOTEXIST999", path=".")
    assert "无匹配" in result or result == "(无匹配结果)"


async def test_search_content_invalid_regex_returns_error(workspace, monkeypatch):
    monkeypatch.setattr(file_tools, "_RG_BIN", None)
    result = await search_content("[invalid(regex", path=".")
    assert "error" in result.lower()


async def test_search_content_python_fallback(workspace, monkeypatch):
    monkeypatch.setattr(file_tools, "_RG_BIN", None)
    _make_tree(workspace)
    result = await search_content("def foo", path=".")
    assert "a.py" in result
    assert "def foo" in result


async def test_search_content_single_file(workspace):
    (workspace / "single.py").write_text("line1\nTARGET\nline3\n")
    result = await search_content("TARGET", path="single.py")
    assert "TARGET" in result


async def test_search_content_escape_rejected(workspace):
    result = await search_content("password", path="/etc")
    assert "error" in result.lower()


async def test_search_content_traversal_rejected(workspace):
    result = await search_content("password", path="../..")
    assert "error" in result.lower()


# ── search_files ──────────────────────────────────────────────────────────────


async def test_search_files_glob_pattern(workspace):
    _make_tree(workspace)
    result = await search_files("*.py", path=".")
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


async def test_search_files_recursive_glob(workspace):
    _make_tree(workspace)
    result = await search_files("**/*.py", path=".")
    assert "d.py" in result


async def test_search_files_sorted_by_mtime(workspace):
    import time

    (workspace / "old.py").write_text("x")
    time.sleep(0.01)
    (workspace / "new.py").write_text("y")
    result = await search_files("*.py", path=".")
    assert result.index("new.py") < result.index("old.py")


async def test_search_files_max_results_truncation(workspace):
    for i in range(20):
        (workspace / f"f{i:02d}.py").write_text("x")
    result = await search_files("*.py", path=".", max_results=5)
    assert "截断" in result


async def test_search_files_no_match(workspace):
    _make_tree(workspace)
    result = await search_files("*.xyz", path=".")
    assert "无匹配" in result or result == "(无匹配文件)"


async def test_search_files_python_fallback(workspace, monkeypatch):
    monkeypatch.setattr(file_tools, "_RG_BIN", None)
    _make_tree(workspace)
    result = await search_files("*.py", path=".")
    assert "a.py" in result
    assert "b.py" in result


async def test_search_files_escape_rejected(workspace):
    result = await search_files("*.py", path="/etc")
    assert "error" in result.lower()
