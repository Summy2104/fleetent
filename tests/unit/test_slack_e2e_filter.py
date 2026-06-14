"""Unit: helper 的「按 bot_user_id + cursor 过滤新消息」纯函数。"""

from __future__ import annotations

from tests.e2e.slack_autonomous._pure import filter_new_bot_messages


def test_returns_only_bot_messages_after_cursor() -> None:
    msgs = [
        {"user": "UBOT", "ts": "100.000100", "text": "old bot"},
        {"user": "UME", "ts": "150.000100", "text": "my own msg"},
        {"user": "UBOT", "ts": "200.000100", "text": "new bot"},
    ]
    out = filter_new_bot_messages(msgs, bot_user_id="UBOT", after_ts="120.0")
    assert [m["text"] for m in out] == ["new bot"]


def test_excludes_own_and_at_or_before_cursor() -> None:
    msgs = [
        {"user": "UME", "ts": "300.0", "text": "me"},
        {"user": "UBOT", "ts": "50.0", "text": "old"},
        {"user": "UBOT", "ts": "120.0", "text": "exactly at cursor"},
    ]
    out = filter_new_bot_messages(msgs, bot_user_id="UBOT", after_ts="120.0")
    assert out == []


def test_no_cursor_returns_all_bot_messages() -> None:
    msgs = [
        {"user": "UBOT", "ts": "1.0", "text": "a"},
        {"user": "UME", "ts": "2.0", "text": "b"},
        {"user": "UBOT", "ts": "3.0", "text": "c"},
    ]
    out = filter_new_bot_messages(msgs, bot_user_id="UBOT", after_ts=None)
    assert [m["text"] for m in out] == ["a", "c"]


def test_result_is_ascending_by_ts() -> None:
    msgs = [
        {"user": "UBOT", "ts": "300.0", "text": "later"},
        {"user": "UBOT", "ts": "200.0", "text": "earlier"},
    ]
    out = filter_new_bot_messages(msgs, bot_user_id="UBOT", after_ts="100.0")
    assert [m["text"] for m in out] == ["earlier", "later"]
