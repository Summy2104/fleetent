"""Slack status keeper: heartbeat keepalive + elapsed, last-label memory (im-progress-heartbeat)."""

from __future__ import annotations

from fleetent.im_gateway import slack


def test_tool_call_sets_label_then_heartbeat_appends_elapsed() -> None:
    keeper = slack._SlackStatusKeeper()
    status, _loading = keeper.text_and_loading(
        {"type": "tool_call", "names": ["run_code"]}
    )
    assert status != slack._THINKING_STATUS  # a tool-specific label, not the default

    hb_status, hb_loading = keeper.text_and_loading({"type": "heartbeat", "elapsed_s": 45})
    assert hb_status == f"{status} · 已 45s"
    # loading messages preserved from the last tool batch (not reset)
    assert hb_loading == _loading


def test_heartbeat_before_any_tool_uses_thinking() -> None:
    keeper = slack._SlackStatusKeeper()
    status, _ = keeper.text_and_loading({"type": "heartbeat", "elapsed_s": 3})
    assert status == f"{slack._THINKING_STATUS} · 已 3s"


def test_heartbeat_does_not_clear_last_label() -> None:
    keeper = slack._SlackStatusKeeper()
    tool_status, _ = keeper.text_and_loading({"type": "tool_call", "names": ["web_search"]})
    keeper.text_and_loading({"type": "heartbeat", "elapsed_s": 10})
    # a later heartbeat still reflects the tool label, not cleared
    again, _ = keeper.text_and_loading({"type": "heartbeat", "elapsed_s": 20})
    assert again == f"{tool_status} · 已 20s"
