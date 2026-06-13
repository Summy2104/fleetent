"""Unit: 审批指令文本匹配容忍 leading @mention（频道场景需 @bot）。

频道里消息必须 @bot 才被 agent 收到，event.text 带 leading `<@id>`；匹配 `_APPROVAL_RE`
前需剥离它，否则 `^(approve|reject)` 不匹配。DM 不带 @、自然语言不得误伤。
"""

from __future__ import annotations

from fleetent.im_gateway.normalizer import (
    _match_approval_command,
    _strip_leading_mention,
)


def test_strip_leading_mention_plain() -> None:
    assert _strip_leading_mention("<@U123> approve abc123") == "approve abc123"


def test_strip_leading_mention_with_label() -> None:
    assert _strip_leading_mention("<@U123|bot> approve abc123") == "approve abc123"


def test_strip_no_mention_unchanged() -> None:
    assert _strip_leading_mention("approve abc123") == "approve abc123"


def test_strip_only_one_leading_mention() -> None:
    # 只剥开头一个；审批指令的 mention 必在首
    assert _strip_leading_mention("<@U1> <@U2> approve abc123") == "<@U2> approve abc123"


def test_match_channel_with_mention() -> None:
    m = _match_approval_command("<@U0B8MEKAM44> approve 72a6eb86")
    assert m is not None
    assert m.group(1).lower() == "approve"
    assert m.group(3) == "72a6eb86"


def test_match_dm_without_mention() -> None:
    m = _match_approval_command("approve 72a6eb86")
    assert m is not None
    assert m.group(3) == "72a6eb86"


def test_match_reject_with_mention() -> None:
    m = _match_approval_command("<@U123> reject abc123def")
    assert m is not None
    assert m.group(1).lower() == "reject"


def test_match_approve_always_with_mention() -> None:
    m = _match_approval_command("<@U123|bot> approve always abc123")
    assert m is not None
    assert m.group(2) is not None  # "always" 捕获组


def test_prose_with_mention_not_matched() -> None:
    # 剥离 mention 后 id 格式校验失败 → 不当审批
    assert _match_approval_command("<@U123> approve the plan") is None


def test_plain_mention_message_not_matched() -> None:
    assert _match_approval_command("<@U123> 你好，帮我查个数据") is None
