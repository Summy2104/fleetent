"""Fired-task silent-sentinel detection is robust to trailing content (no leak)."""

from __future__ import annotations

from fleetent.cron_scheduler import _is_silent_reply


def test_exact_sentinel_is_silent():
    assert _is_silent_reply("[SILENT]") is True


def test_sentinel_with_trailing_trailer_is_silent():
    # The historical leak: a delivery trailer appended after the sentinel.
    assert _is_silent_reply("[SILENT]\n\n📬 实际投递：消息 1（U09…UQ3）") is True


def test_sentinel_with_surrounding_whitespace_is_silent():
    assert _is_silent_reply("  [SILENT]  ") is True
    assert _is_silent_reply("\n[SILENT]\n") is True


def test_none_and_blank_are_silent():
    assert _is_silent_reply(None) is True
    assert _is_silent_reply("") is True
    assert _is_silent_reply("   ") is True


def test_real_broadcast_is_not_silent():
    assert _is_silent_reply("当前金价 4217.4 美元/盎司") is False


def test_sentinel_with_same_line_extra_is_not_silent():
    # Model put real content on the first line → it wants to publish, not skip.
    assert _is_silent_reply("[SILENT] 你好") is False
