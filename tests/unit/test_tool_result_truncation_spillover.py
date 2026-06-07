"""Tests for upgraded spillover truncation (tool-result-truncation spec MODIFIED/ADDED)."""

from __future__ import annotations

import fleetent.tools.result_truncation as trt


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


# ── threshold is now 50KB ────────────────────────────────────────────────────


def test_default_threshold_is_50kb():
    assert trt.MAX_TOOL_RESULT_BYTES == 50_000


def test_within_50kb_returned_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    s = "x" * 49_000
    result = trt.truncate_tool_result(s)
    assert result == s
    assert not (tmp_path / "spillover").exists()


# ── spillover file written on overflow ───────────────────────────────────────


def test_overflow_writes_spillover_file(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    big = "line content\n" * 6_000  # > 50KB
    trt.truncate_tool_result(big)
    files = list((tmp_path / "spillover").iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".txt"
    assert files[0].read_text(encoding="utf-8") == big


def test_overflow_spillover_file_contains_full_content(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    big = ("hello world\n") * 6_000
    trt.truncate_tool_result(big)
    spill_file = next((tmp_path / "spillover").iterdir())
    assert spill_file.read_text(encoding="utf-8") == big


# ── preview is first 100 lines (not bytes) ───────────────────────────────────


def test_overflow_result_contains_first_100_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    # Each line ~210 bytes so 500 lines = ~105KB > 50KB threshold
    lines = [f"UNIQUE_LINE_{i:04d}:" + "x" * 200 for i in range(500)]
    big = "\n".join(lines) + "\n"
    assert _nbytes(big) > 50_000
    result = trt.truncate_tool_result(big)
    for i in range(100):
        assert f"UNIQUE_LINE_{i:04d}:" in result
    assert "UNIQUE_LINE_0100:" not in result


def test_overflow_hint_shows_actual_count_when_fewer_than_100_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    # 60 lines totaling > 50KB; hint should say "60 行" not "100 行"
    lines = ["x" * 900 for _ in range(60)]  # 60 * 900 = 54KB > 50KB
    big = "\n".join(lines) + "\n"
    assert _nbytes(big) > 50_000
    result = trt.truncate_tool_result(big)
    assert "60 行" in result


# ── spillover path and hint in result ────────────────────────────────────────


def test_overflow_result_contains_spillover_path(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    big = "data-line\n" * 6_000  # ~60KB > 50KB
    result = trt.truncate_tool_result(big)
    spill_file = next((tmp_path / "spillover").iterdir())
    assert str(spill_file) in result


def test_overflow_result_contains_read_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    big = "data-line\n" * 6_000  # ~60KB > 50KB
    result = trt.truncate_tool_result(big)
    assert "read_file" in result
    assert "offset" in result


# ── self_truncates tools skip spillover ──────────────────────────────────────


def test_self_truncates_tools_use_old_head_tail_path(tmp_path, monkeypatch):
    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    big = "x" * 100_000
    result = trt.truncate_tool_result(big, self_truncates=True)
    # Old path: no spillover file
    assert not (tmp_path / "spillover").exists()
    # Still truncated to max bytes
    assert _nbytes(result) <= trt.MAX_TOOL_RESULT_BYTES


# ── cleanup helper ────────────────────────────────────────────────────────────


def test_cleanup_removes_old_files(tmp_path):
    import time

    spillover = tmp_path / "spillover"
    spillover.mkdir()
    old_file = spillover / "old.txt"
    old_file.write_text("old data")
    # Back-date mtime to 8 days ago
    old_mtime = time.time() - 8 * 86400
    import os

    os.utime(old_file, (old_mtime, old_mtime))

    fresh_file = spillover / "fresh.txt"
    fresh_file.write_text("fresh data")

    trt.cleanup_spillover(spillover_dir=spillover, max_age_days=7)

    assert not old_file.exists()
    assert fresh_file.exists()
