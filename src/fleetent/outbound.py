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
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """Send text to target on platform. Returns True on success, False on any failure.

    ``target_type`` selects DM (``user``) vs a channel/group post (``channel``);
    ``thread`` optionally threads the message (Slack ``thread_ts`` / Telegram topic).
    ``blocks`` is an optional platform-specific rich payload (Slack Block Kit);
    platforms without rich rendering ignore it and send the text fallback.
    """
    if platform == "slack":
        if target_type == "channel":
            return await _slack_send_channel(connector, target, text, thread, blocks)
        return await _slack_send_dm(connector, target, text, blocks)
    if platform == "telegram":
        return await _telegram_send(connector, target, text, thread)
    logger.warning("outbound_unsupported_platform", platform=platform)
    return False


async def send_file_to(
    platform: str,
    connector: Any,
    target: str,
    path: str,
    *,
    target_type: str = "user",
    thread: Any = None,
) -> bool:
    """Send a local file as an attachment to target on platform.

    Returns True on success, False on any failure (mirrors ``send_to`` semantics —
    delivery failure is logged and swallowed, never raised). ``target_type`` selects
    DM (``user``) vs a channel post (``channel``); ``thread`` optionally threads the
    delivery (Slack ``thread_ts``). This is the single outbound file delivery point
    shared by the ``send_file`` tool and the IM adapters' upload path.
    """
    if platform == "slack":
        return await _slack_send_file(connector, target, path, target_type, thread)
    if platform == "telegram":
        return await _telegram_send_file(connector, target, path)
    logger.warning("outbound_file_unsupported_platform", platform=platform)
    return False


def approval_prompt_blocks(
    approval_id: str, tool_name: str, risk_level: str
) -> list[dict[str, Any]]:
    """Slack Block Kit payload for an approval prompt: summary + three decision buttons.

    The gate passes this payload opaquely; only Slack delivery paths render it.
    Button action_ids are the contract consumed by the Slack ``block_actions`` handler.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔐 工具 `{tool_name}` 请求执行（风险等级: {risk_level}）\n"
                    f"Approval ID: `{approval_id}`"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "approval_approve",
                    "text": {"type": "plain_text", "text": "✅ 批准"},
                    "style": "primary",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "action_id": "approval_reject",
                    "text": {"type": "plain_text", "text": "❌ 拒绝"},
                    "style": "danger",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "action_id": "approval_approve_always",
                    "text": {"type": "plain_text", "text": "✅ 始终允许"},
                    "value": approval_id,
                },
            ],
        },
    ]


async def _slack_send_channel(
    client: Any,
    channel: str,
    text: str,
    thread: Any = None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread:
            kwargs["thread_ts"] = thread
        if blocks is not None:
            kwargs["blocks"] = blocks
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


async def _slack_send_dm(
    client: Any, user_id: str, text: str, blocks: list[dict[str, Any]] | None = None
) -> bool:
    try:
        result = await client.conversations_open(users=[user_id])
        channel = result["channel"]["id"]
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        await client.chat_postMessage(**kwargs)
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


async def _slack_send_file(
    client: Any, target: str, path: str, target_type: str, thread: Any
) -> bool:
    """Upload a local file to Slack via ``files_upload_v2``.

    For a channel post the ``target`` is the channel id used directly; for a DM the
    ``target`` is a user id, resolved to its DM channel via ``conversations_open``
    (same range as ``_slack_send_dm``). A single delivery failure is logged and
    swallowed so the caller's run continues.
    """
    try:
        if target_type == "channel":
            channel = target
        else:
            result = await client.conversations_open(users=[target])
            channel = result["channel"]["id"]
        await client.files_upload_v2(channel=channel, thread_ts=thread, file=path)
        return True
    except Exception as exc:  # noqa: BLE001 — outbound file failure must not abort the caller
        logger.warning("slack_send_file_failed", target=target, path=path, error=str(exc))
        return False


async def _telegram_send_file(bot: Any, chat_id: str, path: str) -> bool:
    """Send a local file to a Telegram chat via ``bot.send_document``."""
    try:
        await bot.send_document(chat_id=chat_id, document=path)
        return True
    except Exception as exc:  # noqa: BLE001 — outbound file failure must not abort the caller
        logger.warning("telegram_send_file_failed", chat_id=chat_id, path=path, error=str(exc))
        return False


async def _telegram_is_reachable(bot: Any, chat_id: str) -> bool:
    """Reachable only if the user has previously /started the bot (chat exists)."""
    try:
        await bot.get_chat(chat_id=chat_id)
        return True
    except Exception:  # noqa: BLE001 — not reachable if any error
        return False
