"""Unit: 频道场景给消息加 bot @mention 的纯函数（真实验证暴露：频道必须 @bot）。"""

from __future__ import annotations

from tests.e2e.slack_autonomous._pure import prepend_mention


def test_prepends_bot_mention() -> None:
    assert prepend_mention("你好", "UBOT") == "<@UBOT> 你好"


def test_empty_bot_returns_text_unchanged() -> None:
    assert prepend_mention("你好", "") == "你好"
    assert prepend_mention("你好", None) == "你好"


def test_empty_text_still_mentions() -> None:
    assert prepend_mention("", "UBOT") == "<@UBOT> "
