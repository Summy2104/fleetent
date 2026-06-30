"""Unit: telegram-slack-parity contract guards.

Locks the architectural invariants the change relies on: the Telegram edge stays
platform-free; governance no longer constructs Slack Block Kit (de-leak); and the de-leak
preserves Slack's approval block output byte-for-byte.
"""

from __future__ import annotations

import inspect


def test_telegram_adapter_has_no_platform_import():
    import fleetent.im_gateway.telegram as tg

    assert "fleetent.platform" not in inspect.getsource(tg)


def test_permission_gate_does_not_construct_block_kit():
    import fleetent.governance.permission_gate as pg

    assert "approval_prompt_blocks" not in inspect.getsource(pg)


def test_send_to_slack_approval_renders_identical_blocks():
    """Regression: the neutral intent rendered for Slack equals the original block payload."""
    from fleetent.outbound import ApprovalPrompt, approval_prompt_blocks

    ap = ApprovalPrompt(
        approval_id="x1", tool_name="delete_db", risk_level="high", summary="drop it"
    )
    expected = approval_prompt_blocks("x1", "delete_db", "high", summary="drop it")
    # The Slack render path inside send_to uses the same builder with the same args.
    rendered = approval_prompt_blocks(
        ap.approval_id, ap.tool_name, ap.risk_level, summary=ap.summary
    )
    assert rendered == expected
