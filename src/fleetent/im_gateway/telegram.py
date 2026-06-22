from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Telegram photos carry no explicit MIME; they are served as JPEG.
_TELEGRAM_PHOTO_MIME = "image/jpeg"


async def _send_typing_for_progress(bot: Any, chat_id: str, evt: dict[str, Any]) -> None:
    """Re-arm Telegram's ~5s typing indicator for any progress event.

    im-progress-heartbeat: the typing action self-expires after ~5s, so it must be
    re-sent periodically — heartbeat events (emitted by the agent loop during long
    LLM calls / tools / sub_agent runs) drive exactly that. Event content is irrelevant
    (any progress event re-arms typing). Best-effort: a send failure is swallowed.
    """
    try:  # noqa: SIM105 — contextlib.suppress would obscure the awaited call
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:  # noqa: BLE001 — typing action is non-critical
        pass


async def _download_photo_attachments(message: Any, context: Any) -> list[tuple[bytes, str]]:
    """Download the largest PhotoSize of a Telegram message, if any.

    Best-effort: a download failure is logged and degrades to no attachments
    rather than aborting the message. The last PhotoSize is the highest
    resolution.
    """
    photos = getattr(message, "photo", None)
    if not photos:
        return []
    largest = photos[-1]
    try:
        tg_file = await context.bot.get_file(largest.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as exc:  # noqa: BLE001 — best-effort download, must not abort handler
        logger.warning("telegram_photo_download_failed", error=str(exc))
        return []
    return [(bytes(data), _TELEGRAM_PHOTO_MIME)]


def _derive_session_id(chat_type: str, user_id: int, reply_to_id: int | None) -> str:
    if chat_type == "private":
        return f"user:{user_id}"
    if reply_to_id is not None:
        return f"thread:{reply_to_id}"
    return f"user:{user_id}"


def create_app(agent_name: str, config: dict[str, Any]) -> object:
    """Create a python-telegram-bot Application bound to one agent's Telegram connection.

    The receiving connection identifies the agent (per-agent-telegram-connector): the
    handler stamps ``agent_name`` so routing skips channel→agent lookup. The connector
    identity is the owning agent name, passed through to the injected IM identity
    resolver; chat access is enforced by the access gate.
    """
    try:
        from telegram.ext import Application
    except ImportError:
        raise RuntimeError("python-telegram-bot not installed") from None

    bot_token = config.get("bot_token", "")
    builder = Application.builder().token(bot_token).concurrent_updates(True)
    application = builder.build()

    async def handle_message(update: object, context: object) -> None:
        from telegram import Update

        from fleetent.im_gateway.access import (  # noqa: PLC0415
            IMIdentityResolutionError,
            resolve_identity,
        )
        from fleetent.im_gateway.normalizer import (  # noqa: PLC0415
            NormalizedMessage,
            SessionContext,
            route,
        )
        from fleetent.outbound import ConversationAddress  # noqa: PLC0415

        assert isinstance(update, Update)
        if not update.message or not update.effective_user:
            return

        channel_id = str(update.message.chat.id)

        tg_user_id = update.effective_user.id
        # Identity is the platform-native id, resolved locally — no platform user_store.
        try:
            identity = resolve_identity("telegram", str(tg_user_id), agent_name)
        except IMIdentityResolutionError as exc:
            logger.warning(
                "telegram_identity_resolution_rejected",
                agent=agent_name,
                platform_user_id=str(tg_user_id),
                error=str(exc),
            )
            return

        reply_to = update.message.reply_to_message
        chat_type = update.message.chat.type

        session_id = _derive_session_id(
            chat_type=chat_type,
            user_id=tg_user_id,
            reply_to_id=reply_to.message_id if reply_to else None,
        )

        async def reply_func(text: str) -> None:
            await update.message.reply_text(text)  # type: ignore[union-attr]

        async def progress_func(evt: dict) -> None:  # type: ignore[type-arg]
            await _send_typing_for_progress(context.bot, channel_id, evt)  # type: ignore[attr-defined]

        attachments = await _download_photo_attachments(update.message, context)
        # Image messages carry their text in `caption`, not `text`.
        text = update.message.caption or update.message.text or ""

        msg = NormalizedMessage(
            platform="telegram",
            agent_name=agent_name,
            session_id=session_id,
            session_context=SessionContext(
                platform="telegram",
                sender_id=str(tg_user_id),
                sender_name=update.effective_user.full_name or "",
                chat_type="dm" if chat_type == "private" else "channel",
                channel_name=channel_id,
                was_mentioned=False,
                thread_root=str(reply_to.message_id) if reply_to else "",
            ),
            user_id=identity,
            text=text,
            attachments=attachments,
            reply_func=reply_func,
            progress_func=progress_func,
            channel_id=channel_id,
            outbound_connectors={"telegram": context.bot},
            conversation_address=ConversationAddress(
                platform="telegram",
                chat_id=channel_id,
                target_type="user",
                thread_id=None,
                user_id=str(tg_user_id),
                chat_type="dm" if chat_type == "private" else "channel",
                thread_root=str(reply_to.message_id) if reply_to else "",
            ),
        )
        await route(msg)

    from telegram.ext import MessageHandler, filters

    application.add_handler(
        MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message)
    )
    return application


async def _run_polling(app: object) -> None:
    """Start polling and serve until cancelled (network seam)."""
    await app.initialize()  # type: ignore[attr-defined]
    await app.start()  # type: ignore[attr-defined]
    await app.updater.start_polling()  # type: ignore[attr-defined]
    # Polling runs in its own task; block here until the manager cancels us.
    await asyncio.Event().wait()


async def run(agent_name: str, config: dict[str, Any]) -> None:
    """Run one agent's Telegram connection until cancelled (network seam).

    Per-agent connection status is owned by the connector supervisor, which catches
    errors here and records them per agent. This runner just opens the connection.
    """
    from fleetent.im_gateway import connector_registry

    app = create_app(agent_name, config)
    # Register the live bot so the cron scheduler can deliver fired-task replies to this
    # agent's Telegram at fire time (resolved per fire, cleared on disconnect).
    bot = getattr(app, "bot", None)
    if bot is not None:
        connector_registry.register("telegram", agent_name, bot)
    try:
        await _run_polling(app)
    finally:
        connector_registry.unregister("telegram", agent_name)
