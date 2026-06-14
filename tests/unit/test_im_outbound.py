"""Unit tests for im_gateway outbound send primitives (A1).

Tests send_to() and is_reachable() — mocked Slack/Telegram HTTP, no real connections.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

# ── send_to: Slack ─────────────────────────────────────────────────────────────


async def test_send_to_slack_opens_dm_then_posts() -> None:
    """send_to("slack") must open a DM channel then call chat_postMessage."""
    from fleetent.im_gateway.outbound import send_to

    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_CHANNEL_123"}})
    client.chat_postMessage = AsyncMock(return_value={"ok": True})

    result = await send_to("slack", client, "U_USER_456", "hello approver")

    assert result.ok is True
    client.conversations_open.assert_called_once_with(users=["U_USER_456"])
    client.chat_postMessage.assert_called_once_with(channel="DM_CHANNEL_123", text="hello approver")


async def test_send_to_slack_returns_false_on_failure() -> None:
    """send_to("slack") must return False when the Slack API raises."""
    from fleetent.im_gateway.outbound import send_to

    client = AsyncMock()
    client.conversations_open = AsyncMock(side_effect=RuntimeError("network error"))

    result = await send_to("slack", client, "U_BAD", "text")

    assert result.ok is False


# ── send_to: Telegram ──────────────────────────────────────────────────────────


async def test_send_to_telegram_calls_send_message() -> None:
    """send_to("telegram") must call bot.send_message with the given chat_id and text."""
    from fleetent.im_gateway.outbound import send_to

    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    result = await send_to("telegram", bot, "987654321", "you must approve this")

    assert result.ok is True
    bot.send_message.assert_called_once_with(chat_id="987654321", text="you must approve this")


async def test_send_to_telegram_returns_false_on_failure() -> None:
    """send_to("telegram") must return False when the bot API raises."""
    from fleetent.im_gateway.outbound import send_to

    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("forbidden"))

    result = await send_to("telegram", bot, "UNKNOWN", "text")

    assert result.ok is False


async def test_send_to_unknown_platform_returns_false() -> None:
    """send_to with an unknown platform should return False, not raise."""
    from fleetent.im_gateway.outbound import send_to

    result = await send_to("whatsapp", MagicMock(), "target", "text")
    assert result.ok is False


# ── send_to: independent of inbound context ──────────────────────────────────


# ── is_reachable ──────────────────────────────────────────────────────────────


async def test_is_reachable_slack_always_true() -> None:
    """Any Slack workspace user is reachable — no API call needed."""
    from fleetent.im_gateway.outbound import is_reachable

    client = AsyncMock()
    result = await is_reachable("slack", client, "U_ANYONE")

    assert result is True
    client.conversations_open.assert_not_called()


async def test_is_reachable_telegram_returns_false_for_unknown_chat_id() -> None:
    """Telegram user who never /started the bot — get_chat raises → not reachable."""
    from fleetent.im_gateway.outbound import is_reachable

    bot = AsyncMock()
    bot.get_chat = AsyncMock(side_effect=RuntimeError("chat not found"))

    result = await is_reachable("telegram", bot, "UNKNOWN_CHAT_ID")

    assert result is False
    bot.get_chat.assert_called_once_with(chat_id="UNKNOWN_CHAT_ID")


async def test_is_reachable_telegram_returns_true_for_known_chat_id() -> None:
    """Telegram user who previously /started the bot — get_chat succeeds → reachable."""
    from fleetent.im_gateway.outbound import is_reachable

    bot = AsyncMock()
    bot.get_chat = AsyncMock(return_value=MagicMock())

    result = await is_reachable("telegram", bot, "123456789")

    assert result is True


async def test_is_reachable_unknown_platform_returns_false() -> None:
    """Unknown platform is never reachable."""
    from fleetent.im_gateway.outbound import is_reachable

    result = await is_reachable("whatsapp", MagicMock(), "target")
    assert result is False


# ── send_to: independent of inbound context ──────────────────────────────────


async def test_send_to_slack_requires_no_inbound_event() -> None:
    """send_to must not require reply_thread/trigger event to operate."""
    from fleetent.im_gateway.outbound import send_to

    # Client with no pre-existing thread state
    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_NEW"}})
    client.chat_postMessage = AsyncMock(return_value={"ok": True})

    # Called with just platform, connector, target, text — no thread context
    result = await send_to("slack", client, "U_FRESH", "standalone message")

    assert result.ok is True
    # Must open a new DM, not reply into an existing thread
    client.conversations_open.assert_called_once()


# ── 1.5 Guard: no platform imports ────────────────────────────────────────────


def test_outbound_module_has_no_platform_imports() -> None:
    """im_gateway.outbound MUST NOT import fleetent.platform.* or fleetent.user_store."""
    import fleetent.im_gateway.outbound as outbound_mod

    source = inspect.getsource(outbound_mod)
    assert "fleetent.platform" not in source, "outbound must not import fleetent.platform.*"
    assert "fleetent.user_store" not in source, "outbound must not import fleetent.user_store"


# ── approval prompt blocks (slack-approval-buttons) ───────────────────────────


def test_approval_prompt_blocks_carry_three_actions_with_id() -> None:
    """Blocks include approve / reject / approve_always buttons valued with the id."""
    from fleetent.outbound import approval_prompt_blocks

    blocks = approval_prompt_blocks("appr-42", "send_im_message", "medium")

    actions = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions) == 1
    by_action_id = {e["action_id"]: e for e in actions[0]["elements"]}
    assert set(by_action_id) == {"approval_approve", "approval_reject", "approval_approve_always"}
    assert all(e["value"] == "appr-42" for e in by_action_id.values())


def test_approval_prompt_blocks_include_text_section_with_tool() -> None:
    """A section block names the tool and risk so the prompt reads standalone."""
    from fleetent.outbound import approval_prompt_blocks

    blocks = approval_prompt_blocks("appr-43", "run_code", "high")

    sections = [b for b in blocks if b.get("type") == "section"]
    joined = " ".join(str(s) for s in sections)
    assert "run_code" in joined
    assert "appr-43" in joined


async def test_send_to_slack_dm_forwards_blocks() -> None:
    """send_to(..., blocks=...) passes blocks to chat_postMessage on the DM path."""
    from fleetent.im_gateway.outbound import send_to

    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "DM_1"}})
    client.chat_postMessage = AsyncMock(return_value={"ok": True})
    blocks = [{"type": "actions", "elements": []}]

    result = await send_to("slack", client, "U_X", "fallback text", blocks=blocks)

    assert result.ok is True
    kwargs = client.chat_postMessage.call_args.kwargs
    assert kwargs["blocks"] == blocks
    assert kwargs["text"] == "fallback text"


async def test_send_to_telegram_ignores_blocks() -> None:
    """Telegram path accepts the blocks kwarg but does not forward it."""
    from fleetent.im_gateway.outbound import send_to

    bot = AsyncMock()
    bot.send_message = AsyncMock()

    result = await send_to("telegram", bot, "12345", "hello", blocks=[{"type": "actions"}])

    assert result.ok is True
    assert "blocks" not in (bot.send_message.call_args.kwargs or {})
