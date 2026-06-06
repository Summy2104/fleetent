"""Tests for search_content and search_files (builtin-file-tools spec)."""

from __future__ import annotations

import pytest

from fleetent.tools.file_tools import search_content, search_files


def _make_tree(tmp_path):
    """Create a small file tree for search tests."""
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    (tmp_path / "b.py").write_text("import os\ndef baz():\n    return os.getcwd()\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("hello world\nfoo bar\n")
    (tmp_path / "sub" / "d.py").write_text("x = 42\n")
    return tmp_path


# ── search_content ────────────────────────────────────────────────────────────


def test_search_content_finds_pattern(tmp_path):
    _make_tree(tmp_path)
    result = search_content("def foo", path=str(tmp_path))
    assert "a.py" in result
    assert "def foo" in result


def test_search_content_format_file_line_content(tmp_path):
    _make_tree(tmp_path)
    result = search_content("return 1", path=str(tmp_path))
    # Format: filepath:lineno:content
    assert ":" in result
    assert "return 1" in result


def test_search_content_respects_include_filter(tmp_path):
    _make_tree(tmp_path)
    result = search_content("foo", path=str(tmp_path), include="*.py")
    # c.txt has "foo bar" but should be excluded
    assert "c.txt" not in result


def test_search_content_max_results_truncation(tmp_path):
    root = tmp_path / "many"
    root.mkdir()
    for i in range(20):
        (root / f"f{i}.py").write_text("\n".join(f"match_{j}" for j in range(10)) + "\n")
    result = search_content("match_", path=str(root), max_results=5)
    assert "截断" in result or "5" in result


def test_search_content_no_match_returns_no_results(tmp_path):
    _make_tree(tmp_path)
    result = search_content("XYZNOTEXIST999", path=str(tmp_path))
    assert "无匹配" in result or "(no match" in result.lower() or result == "(无匹配结果)"


def test_search_content_invalid_regex_returns_error(tmp_path, monkeypatch):
    # Force Python fallback by hiding rg
    import fleetent.tools.file_tools as ft
    monkeypatch.setattr(ft, "_RG_BIN", None)
    result = search_content("[invalid(regex", path=str(tmp_path))
    assert "error" in result.lower()


def test_search_content_python_fallback(tmp_path, monkeypatch):
    import fleetent.tools.file_tools as ft
    monkeypatch.setattr(ft, "_RG_BIN", None)
    _make_tree(tmp_path)
    result = search_content("def foo", path=str(tmp_path))
    assert "a.py" in result
    assert "def foo" in result


def test_search_content_single_file(tmp_path):
    f = tmp_path / "single.py"
    f.write_text("line1\nTARGET\nline3\n")
    result = search_content("TARGET", path=str(f))
    assert "TARGET" in result


# ── search_files ──────────────────────────────────────────────────────────────


def test_search_files_glob_pattern(tmp_path):
    _make_tree(tmp_path)
    result = search_files("*.py", path=str(tmp_path))
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


def test_search_files_recursive_glob(tmp_path):
    _make_tree(tmp_path)
    result = search_files("**/*.py", path=str(tmp_path))
    assert "d.py" in result  # in sub/


def test_search_files_sorted_by_mtime(tmp_path):
    import time
    old = tmp_path / "old.py"
    new = tmp_path / "new.py"
    old.write_text("x")
    time.sleep(0.01)
    new.write_text("y")
    result = search_files("*.py", path=str(tmp_path))
    assert result.index("new.py") < result.index("old.py")


def test_search_files_max_results_truncation(tmp_path):
    for i in range(20):
        (tmp_path / f"f{i:02d}.py").write_text("x")
    result = search_files("*.py", path=str(tmp_path), max_results=5)
    assert "截断" in result


def test_search_files_no_match(tmp_path):
    _make_tree(tmp_path)
    result = search_files("*.xyz", path=str(tmp_path))
    assert "无匹配" in result or result == "(无匹配文件)"


def test_search_files_python_fallback(tmp_path, monkeypatch):
    import fleetent.tools.file_tools as ft
    monkeypatch.setattr(ft, "_RG_BIN", None)
    _make_tree(tmp_path)
    result = search_files("*.py", path=str(tmp_path))
    assert "a.py" in result
    assert "b.py" in result
