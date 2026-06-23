"""Unit: send_im_message no-ops when the target IS the current conversation.

outbound-tool-no-self-conversation-send: replying to the current conversation is the
harness's job (it delivers the final text reply). A send_im_message to the current
conversation would duplicate that reply, so the tool no-ops (no delivery) and returns
guidance. Proactive outreach to OTHER users/channels is unchanged.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from fleetent.outbound import ConversationAddress, DeliveryReceipt
from fleetent.tools.registry import ToolContext


def _ctx(chat_type="dm", sender="U_ME", channel="C_CHAN"):
    sc = types.SimpleNamespace(
        platform="slack", sender_id=sender, chat_type=chat_type, channel_name=channel
    )
    return ToolContext(
        session_id="S1",
        session_context=sc,
        outbound_connectors={"slack": object()},
        conversation_address=ConversationAddress(
            platform="slack",
            chat_id=channel,
            target_type=chat_type,
            thread_id="T_ROOT",
            user_id=sender,
            chat_type=chat_type,
        ),
    )


def _ok(kind="text"):
    return DeliveryReceipt(ok=True, platform="slack", target="x", target_type="x", kind=kind)


async def test_dm_to_current_sender_is_noop():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok())) as send_to,
    ):
        result = await send_im_message(
            target="U_ME", text="hi", tool_context=_ctx(chat_type="dm", sender="U_ME")
        )

    send_to.assert_not_called()
    assert "未发送" in result


async def test_channel_self_dm_to_current_sender_is_noop():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok())) as send_to,
    ):
        result = await send_im_message(
            target="U1",
            text="hi",
            target_type="user",
            tool_context=_ctx(chat_type="channel", sender="U1"),
        )

    send_to.assert_not_called()
    assert "未发送" in result


async def test_post_to_current_channel_is_noop():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok())) as send_to,
    ):
        result = await send_im_message(
            target="C_CHAN",
            text="hi",
            target_type="channel",
            tool_context=_ctx(chat_type="channel", sender="U1", channel="C_CHAN"),
        )

    send_to.assert_not_called()
    assert "未发送" in result


async def test_third_party_user_still_delivers():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok())) as send_to,
    ):
        result = await send_im_message(
            target="U_OTHER",
            text="hi",
            tool_context=_ctx(chat_type="channel", sender="U1"),
        )

    send_to.assert_called_once()
    assert send_to.call_args.args[2] == "U_OTHER"
    assert "已发送" in result
