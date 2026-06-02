"""Tests for sandbox stdout/stderr truncation (SB6)."""

import fleetent.sandbox_output_truncation as sot


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


# ── truncate function + defaults (group 2/5) ─────────────────────────────────


def test_within_budget_unchanged():
    s = "x" * 100
    assert sot.truncate_stream(s, 1000) == s


def test_over_budget_truncated_within_limit():
    s = "x" * 200_000
    out = sot.truncate_stream(s, 500)
    assert _nbytes(out) <= 500
    assert out != s


def test_default_stdout_50kb_stderr_10kb():
    assert sot.MAX_STDOUT_BYTES == 50 * 1024
    assert sot.MAX_STDERR_BYTES == 10 * 1024


def test_threshold_monkeypatchable(monkeypatch):
    monkeypatch.setattr(sot, "MAX_STDOUT_BYTES", 200)
    out = sot.truncate_stream("y" * 5000, sot.MAX_STDOUT_BYTES)
    assert _nbytes(out) <= 200


# ── head/tail + notice (group 3) ─────────────────────────────────────────────


def test_keeps_head_tail_with_notice():
    s = "HEAD" + ("m" * 5000) + "TAIL"
    out = sot.truncate_stream(s, 200)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "截断" in out and "字节" in out


def test_total_not_over_threshold():
    s = "a" * 50_000
    for limit in (120, 400, 2000):
        assert _nbytes(sot.truncate_stream(s, limit)) <= limit


# ── multibyte-safe (group 4) ─────────────────────────────────────────────────


def test_multibyte_cut_valid_utf8():
    s = "中" * 5000
    out = sot.truncate_stream(s, 205)
    out.encode("utf-8").decode("utf-8")
    assert "�" not in out


# ── separate per-stream limits (group 5) ─────────────────────────────────────


def test_stdout_over_stderr_within_independent():
    big = "x" * 100_000
    small = "ok"
    assert _nbytes(sot.truncate_stream(big, sot.MAX_STDOUT_BYTES)) <= sot.MAX_STDOUT_BYTES
    assert sot.truncate_stream(small, sot.MAX_STDERR_BYTES) == small  # untouched
