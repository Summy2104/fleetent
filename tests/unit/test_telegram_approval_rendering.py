"""Unit: Telegram approval button rendering + callback_data codec (telegram-slack-parity).

Pure data: the inline keyboard mirrors Slack's three decisions (approve / reject /
approve_always); callback_data round-trips (decision, approval_id) and stays within
Telegram's 64-byte limit.
"""

from __future__ import annotations

from fleetent.outbound import (
    ApprovalPrompt,
    approval_callback_data,
    parse_approval_callback,
    render_approval_telegram,
)


def test_callback_data_roundtrip():
    for decision in ("approve", "reject", "approve_always"):
        data = approval_callback_data(decision, "appr-123")
        assert len(data.encode("utf-8")) <= 64
        assert parse_approval_callback(data) == (decision, "appr-123")


def test_parse_rejects_non_approval_prefix():
    assert parse_approval_callback("clarify:sid:0") is None
    assert parse_approval_callback("random") is None


def test_render_telegram_has_three_decision_buttons():
    prompt = ApprovalPrompt(
        approval_id="appr-9", tool_name="run_code", risk_level="medium", summary="do X"
    )
    markup = render_approval_telegram(prompt)
    # python-telegram-bot InlineKeyboardMarkup: .inline_keyboard is a tuple of rows
    buttons = [b for row in markup.inline_keyboard for b in row]
    decisions = {parse_approval_callback(b.callback_data) for b in buttons}
    assert decisions == {
        ("approve", "appr-9"),
        ("reject", "appr-9"),
        ("approve_always", "appr-9"),
    }


def test_approval_prompt_is_neutral_dataclass():
    p = ApprovalPrompt(approval_id="a", tool_name="t", risk_level="high", summary="")
    assert (p.approval_id, p.tool_name, p.risk_level, p.summary) == ("a", "t", "high", "")
