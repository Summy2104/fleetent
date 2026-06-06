"""Tests for upgraded read_file (builtin-file-tools spec)."""

from __future__ import annotations

import pytest

from fleetent.tools.file_tools import read_file


# ── pagination ────────────────────────────────────────────────────────────────


def test_read_file_default_returns_first_200_lines(tmp_path):
    f = tmp_path / "big.txt"
    lines = [f"line {i}" for i in range(500)]
    f.write_text("\n".join(lines) + "\n")
    result = read_file(str(f))
    assert "line 0" in result
    assert "line 199" in result
    assert "line 200" not in result


def test_read_file_offset_starts_at_correct_line(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("\n".join(f"L{i}" for i in range(50)) + "\n")
    result = read_file(str(f), offset=11, limit=5)
    assert "L10" in result
    assert "L9" not in result
    assert "L15" not in result


def test_read_file_limit_caps_lines(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("\n".join(f"row{i}" for i in range(100)) + "\n")
    result = read_file(str(f), offset=1, limit=10)
    assert "row0" in result
    assert "row9" in result
    assert "row10" not in result


def test_read_file_last_page_no_hint(tmp_path):
    f = tmp_path / "short.txt"
    f.write_text("a\nb\nc\n")
    result = read_file(str(f), offset=1, limit=200)
    assert "offset" not in result  # no paging hint when at end


def test_read_file_middle_page_has_hint(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"L{i}" for i in range(500)) + "\n")
    result = read_file(str(f), offset=1, limit=50)
    assert "offset" in result  # paging hint present
    assert "read_file" in result


def test_read_file_shows_line_numbers(tmp_path):
    f = tmp_path / "ln.txt"
    f.write_text("alpha\nbeta\ngamma\n")
    result = read_file(str(f), offset=1, limit=3)
    assert "1" in result
    assert "alpha" in result


# ── directory listing ─────────────────────────────────────────────────────────


def test_read_file_directory_returns_listing(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    result = read_file(str(tmp_path))
    assert "a.py" in result
    assert "b.txt" in result


def test_read_file_directory_shows_sizes(tmp_path):
    (tmp_path / "f.txt").write_text("hello world")
    result = read_file(str(tmp_path))
    assert "f.txt" in result
    # Some size representation present
    assert any(c.isdigit() for c in result)


def test_read_file_directory_truncates_many_entries(tmp_path):
    for i in range(250):
        (tmp_path / f"file_{i:04d}.txt").write_text("x")
    result = read_file(str(tmp_path))
    assert "截断" in result or "truncat" in result.lower()


# ── binary detection ─────────────────────────────────────────────────────────


def test_read_file_png_magic_bytes_detected(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    result = read_file(str(f))
    assert "error" in result.lower() or "二进制" in result
    assert "png" in result.lower() or "image" in result.lower()


def test_read_file_high_non_printable_ratio_detected(tmp_path):
    f = tmp_path / "binary.bin"
    # 40% non-printable bytes (> 30% threshold)
    content = bytes([0x00, 0x01, 0x02, 0x03] * 100) + b"A" * 200
    f.write_bytes(content)
    result = read_file(str(f))
    assert "error" in result.lower() or "二进制" in result


def test_read_file_text_file_not_binary(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("def hello():\n    return 'world'\n")
    result = read_file(str(f))
    assert "def hello" in result
    assert "error" not in result.lower()


# ── error cases ───────────────────────────────────────────────────────────────


def test_read_file_missing_file_returns_error(tmp_path):
    result = read_file(str(tmp_path / "no_such_file.txt"))
    assert "error" in result.lower()
