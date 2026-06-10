"""Unit tests for the Slack approval button action handler (slack-approval-buttons).

The handler maps block_actions clicks to gate decisions using the clicking user's
Slack id, updates the prompt message on success, and shows an ephemeral notice on
an unauthorized/expired click. Gate and Slack client are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def _body(action_id: str, approval_id: str = "appr-1", user: str = "U_CLICKER") -> dict:
    return {
        "user": {"id": user},
        "channel": {"id": "C_PROMPT"},
        "message": {"ts": "1234.5678"},
        "actions": [{"action_id": action_id, "value": approval_id}],
    }


async def test_approve_click_resolves_with_clicker_id_and_updates_message() -> None:
    from fleetent.im_gateway import slack

    ack = AsyncMock()
    client = AsyncMock()
    with patch(
        "fleetent.governance.permission_gate._default_gate.resolve",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(ack, _body("approval_approve"), client)

    ack.assert_called_once()
    kwargs = resolve.call_args.kwargs
    assert kwargs["approval_id"] == "appr-1"
    assert kwargs["decision"] == "approved"
    assert kwargs["approver_user_id"] == "U_CLICKER"
    assert kwargs["always"] is False
    update_kwargs = client.chat_update.call_args.kwargs
    assert update_kwargs["channel"] == "C_PROMPT"
    assert update_kwargs["ts"] == "1234.5678"
    assert update_kwargs["blocks"] == []


async def test_reject_click_resolves_rejected() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.permission_gate._default_gate.resolve",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_reject"), client=client
        )

    assert resolve.call_args.kwargs["decision"] == "rejected"


async def test_approve_always_click_sets_always_flag() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.permission_gate._default_gate.resolve",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_approve_always"), client=client
        )

    kwargs = resolve.call_args.kwargs
    assert kwargs["decision"] == "approved"
    assert kwargs["always"] is True


async def test_unauthorized_click_shows_ephemeral_and_keeps_prompt() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.permission_gate._default_gate.resolve",
        AsyncMock(return_value=False),
    ):
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_approve", user="U_BYSTANDER"), client=client
        )

    client.chat_update.assert_not_called()
    eph_kwargs = client.chat_postEphemeral.call_args.kwargs
    assert eph_kwargs["user"] == "U_BYSTANDER"
    assert eph_kwargs["channel"] == "C_PROMPT"


async def test_reply_func_forwards_blocks_to_say() -> None:
    """The Slack reply_func accepts a blocks kwarg and forwards it to say()."""
    from fleetent.im_gateway.slack import _make_status_funcs

    client = AsyncMock()
    say = AsyncMock()
    reply_func, _ = await _make_status_funcs(client, "C1", "111.222", say)

    blocks = [{"type": "actions", "elements": []}]
    await reply_func("prompt text", blocks=blocks)

    kwargs = say.call_args.kwargs
    assert kwargs["text"] == "prompt text"
    assert kwargs["blocks"] == blocks
