"""Abnormal terminal stops yield a user-facing status reply (never silent)."""

from __future__ import annotations

from fleetent.runtime.loop import (
    _finalize_reply,
    _last_tool_error,
    _terminal_status_reply,
)
from fleetent.runtime.termination import StopReason


def test_last_tool_error_returns_latest_tool_content():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "first error"},
        {"role": "assistant", "content": "..."},
        {"role": "tool", "content": "需要 slackUserId 来定位用户"},
    ]
    assert _last_tool_error(msgs) == "需要 slackUserId 来定位用户"


def test_last_tool_error_normalizes_and_truncates():
    msgs = [{"role": "tool", "content": "  a\n\n  b   c  "}]
    assert _last_tool_error(msgs) == "a b c"
    long = {"role": "tool", "content": "x" * 500}
    assert len(_last_tool_error([long])) == 200


def test_last_tool_error_none_when_no_tool():
    assert _last_tool_error([{"role": "user", "content": "hi"}]) is None
    assert _last_tool_error([{"role": "tool"}]) is None  # no content
    assert _last_tool_error([]) is None


def test_terminal_status_loop_detected_includes_error():
    msgs = [{"role": "tool", "content": "需要 slackUserId 来定位用户"}]
    out = _terminal_status_reply(StopReason.loop_detected, msgs)
    assert out is not None
    assert "停止" in out
    assert "需要 slackUserId 来定位用户" in out
    assert "换" in out  # 提示换方式


def test_terminal_status_consecutive_failures_includes_error():
    msgs = [{"role": "tool", "content": "boom"}]
    out = _terminal_status_reply(StopReason.consecutive_failures, msgs)
    assert out is not None and "boom" in out and "失败" in out


def test_terminal_status_loop_detected_without_tool_is_prefix_only():
    out = _terminal_status_reply(StopReason.loop_detected, [])
    assert out is not None and "停止" in out and "「" not in out


def test_terminal_status_cancelled_and_rejected_have_no_error():
    cancelled = _terminal_status_reply(StopReason.cancelled, [{"role": "tool", "content": "x"}])
    assert cancelled is not None and "取消" in cancelled and "x" not in cancelled
    rejected = _terminal_status_reply(StopReason.approval_rejected, [])
    assert rejected is not None and "批准" in rejected


def test_terminal_status_none_for_self_replying_stops():
    for sr in (
        StopReason.normal,
        StopReason.budget_exceeded,
        StopReason.awaiting_approval,
        StopReason.mcp_strict_unavailable,
    ):
        assert _terminal_status_reply(sr, [{"role": "tool", "content": "x"}]) is None


def test_finalize_reply_keeps_nonempty():
    assert _finalize_reply("hi", StopReason.loop_detected, []) == "hi"
    assert _finalize_reply("done", StopReason.normal, []) == "done"


def test_finalize_reply_substitutes_on_empty_abnormal():
    out = _finalize_reply("", StopReason.loop_detected, [{"role": "tool", "content": "boom"}])
    assert out and "boom" in out
    assert _finalize_reply("   ", StopReason.cancelled, []) == _terminal_status_reply(
        StopReason.cancelled, []
    )


def test_finalize_reply_empty_normal_stays_empty():
    assert _finalize_reply("", StopReason.normal, []) == ""
