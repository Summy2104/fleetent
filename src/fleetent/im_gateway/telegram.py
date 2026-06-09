from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Telegram photos carry no explicit MIME; they are served as JPEG.
_TELEGRAM_PHOTO_MIME = "image/jpeg"


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


def create_app(agent_name: str, owner_id: str, config: dict[str, Any]) -> object:
    """Create a python-telegram-bot Application bound to one agent's Telegram connection.

    The receiving connection identifies the agent (per-agent-telegram-connector): the
    handler stamps ``agent_name`` so routing skips channel→agent lookup. ``owner_id`` still
    scopes user mapping / allowlist. ``config.channels``, when non-empty, filters which
    chats the agent responds in.
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

        from fleetent.im_gateway.access import resolve_identity  # noqa: PLC0415
        from fleetent.im_gateway.normalizer import NormalizedMessage, route  # noqa: PLC0415

        assert isinstance(update, Update)
        if not update.message or not update.effective_user:
            return

        channel_id = str(update.message.chat.id)

        tg_user_id = update.effective_user.id
        # Identity is the platform-native id, resolved locally — no platform user_store.
        identity = resolve_identity("telegram", str(tg_user_id))

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
            try:  # noqa: SIM105 — cannot use contextlib.suppress with async await
                await context.bot.send_chat_action(  # type: ignore[attr-defined]
                    chat_id=channel_id, action="typing"
                )
            except Exception:  # noqa: BLE001 — typing action is non-critical
                pass

        attachments = await _download_photo_attachments(update.message, context)
        # Image messages carry their text in `caption`, not `text`.
        text = update.message.caption or update.message.text or ""

        msg = NormalizedMessage(
            platform="telegram",
            owner_id=owner_id,
            agent_name=agent_name,
            session_id=session_id,
            user_id=identity,
            text=text,
            attachments=attachments,
            reply_func=reply_func,
            progress_func=progress_func,
            channel_id=channel_id,
            outbound_connectors={"telegram": context.bot},
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


async def run(agent_name: str, owner_id: str, config: dict[str, Any]) -> None:
    """Run one agent's Telegram connection until cancelled (network seam).

    Per-agent connection status is owned by the connector supervisor, which catches
    errors here and records them per agent. This runner just opens the connection.
    """
    app = create_app(agent_name, owner_id, config)
    await _run_polling(app)
