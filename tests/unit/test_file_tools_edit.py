"""Tests for edit_file with 6-layer fallback matcher (builtin-file-tools spec)."""

from __future__ import annotations

import pytest

from fleetent.tools.file_tools import edit_file


def _write(tmp_path, name: str, content: str):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


# ── Layer 1: ExactReplacer ────────────────────────────────────────────────────


def test_edit_exact_match(tmp_path):
    f = _write(tmp_path, "f.py", "def foo():\n    return 1\n")
    result = edit_file(str(f), "return 1", "return 42")
    assert "ExactReplacer" in result
    assert f.read_text() == "def foo():\n    return 42\n"


def test_edit_exact_not_found_all_layers_fail(tmp_path):
    f = _write(tmp_path, "f.py", "def foo():\n    return 1\n")
    result = edit_file(str(f), "totally_absent_xyz", "new")
    assert "error" in result.lower()
    assert "6" in result  # tried 6 layers


def test_edit_replace_all_replaces_all_occurrences(tmp_path):
    f = _write(tmp_path, "f.py", "x = 1\ny = 1\nz = 1\n")
    result = edit_file(str(f), "1", "2", replace_all=True)
    assert "替换成功" in result
    assert f.read_text() == "x = 2\ny = 2\nz = 2\n"


def test_edit_replace_first_only_by_default(tmp_path):
    f = _write(tmp_path, "f.py", "a = 1\nb = 1\n")
    edit_file(str(f), "1", "9")
    assert f.read_text() == "a = 9\nb = 1\n"


# ── no-op guard ───────────────────────────────────────────────────────────────


def test_edit_noop_when_identical(tmp_path):
    f = _write(tmp_path, "f.py", "hello\n")
    result = edit_file(str(f), "hello", "hello")
    assert "no-op" in result.lower()
    assert f.read_text() == "hello\n"


# ── Layer 2: LineTrimmedReplacer ─────────────────────────────────────────────


def test_edit_layer2_trailing_whitespace_mismatch(tmp_path):
    f = _write(tmp_path, "f.py", "def foo():\n    return 1\n")
    # old_string has trailing spaces on second line
    result = edit_file(str(f), "def foo():\n    return 1   ", "def foo():\n    return 99")
    assert "替换成功" in result
    assert "return 99" in f.read_text()


# ── Layer 3: WhitespaceNormalizedReplacer ─────────────────────────────────────


def test_edit_layer3_extra_spaces(tmp_path):
    f = _write(tmp_path, "f.py", "x  =  1\n")
    result = edit_file(str(f), "x = 1", "x = 2")
    assert "替换成功" in result
    assert "2" in f.read_text()


# ── Layer 4: LineEndingNormalizedReplacer ─────────────────────────────────────


def test_edit_layer4_crlf_in_file(tmp_path):
    f = _write(tmp_path, "f.txt", "line1\r\nline2\r\n")
    result = edit_file(str(f), "line1\nline2\n", "NEW\n")
    assert "替換成功" in result or "替换成功" in result
    assert "NEW" in f.read_text()


# ── Layer 5: IndentationFlexibleReplacer ─────────────────────────────────────


def test_edit_layer5_different_indentation(tmp_path):
    content = "class A:\n    def method(self):\n        pass\n"
    f = _write(tmp_path, "f.py", content)
    # old_string has no indentation (common-indent stripped)
    result = edit_file(str(f), "def method(self):\n    pass", "def method(self):\n    return 1")
    assert "替换成功" in result


# ── Layer 6: ContextAwareReplacer ────────────────────────────────────────────


def test_edit_layer6_context_anchor(tmp_path):
    content = "def foo():\n    x = 1\n    y = 2\n    return x + y\n"
    f = _write(tmp_path, "f.py", content)
    # old_string has correct first+last line, middle lines with different leading whitespace
    result = edit_file(str(f), "def foo():\nx = 1\ny = 2\nreturn x + y", "def bar():\n    return 3")
    assert "替换成功" in result
    assert "bar" in f.read_text()


# ── missing file ──────────────────────────────────────────────────────────────


def test_edit_missing_file_returns_error(tmp_path):
    result = edit_file(str(tmp_path / "nope.py"), "old", "new")
    assert "error" in result.lower()
