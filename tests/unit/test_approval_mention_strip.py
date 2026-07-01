"""Unit: 审批指令文本匹配容忍 leading @mention（频道场景需 @bot）。

频道里消息必须 @bot 才被 agent 收到，event.text 带 leading `<@id>`；匹配 `_APPROVAL_RE`
前需剥离它，否则 `^(approve|reject)` 不匹配。DM 不带 @、自然语言不得误伤。
"""

from __future__ import annotations

import pytest

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


def test_match_plain_text_mention_prefix() -> None:
    # AAA-8204 ③：DM/Assistant 面板里用户打的 `@R. Alpha` 是纯文本（非 `<@id>`），
    # 且 bot 显示名含空格。剥不掉就漏进主循环 → 审批死循环。须命中。
    m = _match_approval_command("@R. Alpha approve 00b0691a")
    assert m is not None
    assert m.group(1).lower() == "approve"
    assert m.group(3) == "00b0691a"


# tasks.md ③ 回归矩阵：命中 = 三种写法 × approve/reject/always；
# 不命中 = 散文（合法/非法 mention）、缺 id、id 非法。
@pytest.mark.parametrize(
    "text",
    [
        "approve 00b0691a",  # DM 裸命令
        "<@U0B8MEKAM44> approve 00b0691a",  # 频道真实 mention
        "@R. Alpha approve 00b0691a",  # DM 纯文本 @名字（含空格）
        "reject 00b0691a",  # reject
        "approve always 00b0691a",  # always 变体
        "@R. Alpha reject 00b0691a",  # 纯文本 mention + reject
        "@R. Alpha approve always 00b0691a",  # 纯文本 mention + always
    ],
)
def test_approval_command_matrix_match(text: str) -> None:
    assert _match_approval_command(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "@bot approve the plan",  # 纯文本 mention + 散文，id 非法
        "<@U123> approve the plan",  # 真实 mention + 散文，id 非法
        "approve",  # 缺 id
        "approve xyz",  # id 不满足 [a-f0-9-]{6,36}
        "@R. Alpha 你好，帮我查个数据",  # 纯文本 mention 但无审批动词
    ],
)
def test_approval_command_matrix_no_match(text: str) -> None:
    assert _match_approval_command(text) is None


# ③补丁:复制来的命令常带 markdown 代码/加粗格式(反引号/```/**），匹配前须剥掉，否则 id
# 校验失败 → 命令漏进主循环 → 又循环成新审批（实测 approve `5a6decf1` 没命中）。
@pytest.mark.parametrize(
    "text",
    [
        "approve `5a6decf1`",  # 单反引号
        "approve ```5a6decf1```",  # 三反引号
        "approve **5a6decf1**",  # 加粗
        "<@U123> approve `5a6decf1`",  # 真实 mention + 反引号
        "@R. Alpha approve `5a6decf1`",  # 纯文本 mention + 反引号
        "reject `5a6decf1`",
        "approve always `5a6decf1`",
    ],
)
def test_approval_command_strips_markdown_around_id(text: str) -> None:
    m = _match_approval_command(text)
    assert m is not None
    assert m.group(3) == "5a6decf1"
