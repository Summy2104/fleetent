"""Agent-initiated outbound messaging primitives (top-level base infra).

Allows the agent to proactively send messages to specified users/channels,
independent of any inbound message context. Used by the permission gate to
contact designated approvers via DM.

No platform imports — consumed by both governance (permission_gate) and the
IM edge face without creating a core→face dependency.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def send_to(
    platform: str,
    connector: Any,
    target: str,
    text: str,
    *,
    target_type: str = "user",
    thread: Any = None,
) -> bool:
    """Send text to target on platform. Returns True on success, False on any failure.

    ``target_type`` selects DM (``user``) vs a channel/group post (``channel``);
    ``thread`` optionally threads the message (Slack ``thread_ts`` / Telegram topic).
    """
    if platform == "slack":
        if target_type == "channel":
            return await _slack_send_channel(connector, target, text, thread)
        return await _slack_send_dm(connector, target, text)
    if platform == "telegram":
        return await _telegram_send(connector, target, text, thread)
    logger.warning("outbound_unsupported_platform", platform=platform)
    return False


async def _slack_send_channel(client: Any, channel: str, text: str, thread: Any = None) -> bool:
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread:
            kwargs["thread_ts"] = thread
        await client.chat_postMessage(**kwargs)
        return True
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the caller
        logger.warning("slack_send_channel_failed", channel=channel, error=str(exc))
        return False


async def is_reachable(platform: str, connector: Any, target: str) -> bool:
    """Check if target is reachable on platform before sending.

    Encodes platform constraints:
    - Slack: any workspace user is reachable via DM (open channel).
    - Telegram: only users who have previously /started the bot are reachable
      (bot must be able to get their chat info).
    """
    if platform == "slack":
        return True  # Slack workspace users are always reachable via conversations.open
    if platform == "telegram":
        return await _telegram_is_reachable(connector, target)
    return False


async def _slack_send_dm(client: Any, user_id: str, text: str) -> bool:
    try:
        result = await client.conversations_open(users=[user_id])
        channel = result["channel"]["id"]
        await client.chat_postMessage(channel=channel, text=text)
        return True
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the gate
        logger.warning("slack_send_dm_failed", user_id=user_id, error=str(exc))
        return False


async def _telegram_send(bot: Any, chat_id: str, text: str, thread: Any = None) -> bool:
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if thread:
            kwargs["message_thread_id"] = thread
        await bot.send_message(**kwargs)
        return True
    except Exception as exc:  # noqa: BLE001 — outbound failure must not abort the gate
        logger.warning("telegram_send_message_failed", chat_id=chat_id, error=str(exc))
        return False


async def _telegram_is_reachable(bot: Any, chat_id: str) -> bool:
    """Reachable only if the user has previously /started the bot (chat exists)."""
    try:
        await bot.get_chat(chat_id=chat_id)
        return True
    except Exception:  # noqa: BLE001 — not reachable if any error
        return False
