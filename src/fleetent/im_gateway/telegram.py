from __future__ import annotations

import asyncio

import structlog

from fleetent.platform.im_gateway_management import connector_config, connector_store

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0


def _derive_session_id(chat_type: str, user_id: int, reply_to_id: int | None) -> str:
    if chat_type == "private":
        return f"user:{user_id}"
    if reply_to_id is not None:
        return f"thread:{reply_to_id}"
    return f"user:{user_id}"


def create_app(owner_id: str, config: dict[str, str]) -> object:
    """Create and return a configured python-telegram-bot Application."""
    try:
        from telegram.ext import Application
    except ImportError:
        raise RuntimeError("python-telegram-bot not installed") from None

    builder = Application.builder().token(config.get("bot_token", "")).concurrent_updates(True)
    application = builder.build()

    async def handle_message(update: object, context: object) -> None:
        from telegram import Update

        from fleetent.im_gateway.normalizer import NormalizedMessage, route  # noqa: PLC0415
        from fleetent.platform.im_gateway_management.identity import get_or_create  # noqa: PLC0415

        assert isinstance(update, Update)
        if not update.message or not update.effective_user:
            return

        tg_user_id = update.effective_user.id
        user = get_or_create(owner_id, "telegram", str(tg_user_id))

        reply_to = update.message.reply_to_message
        chat_type = update.message.chat.type

        session_id = _derive_session_id(
            chat_type=chat_type,
            user_id=tg_user_id,
            reply_to_id=reply_to.message_id if reply_to else None,
        )

        async def reply_func(text: str) -> None:
            await update.message.reply_text(text)  # type: ignore[union-attr]

        msg = NormalizedMessage(
            platform="telegram",
            owner_id=owner_id,
            session_id=session_id,
            user_id=user.id,
            text=update.message.text or "",
            attachments=[],
            reply_func=reply_func,
            channel_id=str(update.message.chat.id),
        )
        await route(msg)

    from telegram.ext import MessageHandler, filters

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application


async def _run_polling(app: object) -> None:
    """Start polling and serve until cancelled (network seam)."""
    await app.initialize()  # type: ignore[attr-defined]
    await app.start()  # type: ignore[attr-defined]
    await app.updater.start_polling()  # type: ignore[attr-defined]
    # Polling runs in its own task; block here until the manager cancels us.
    await asyncio.Event().wait()


async def _heartbeat_loop(owner_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        connector_store.heartbeat(owner_id, "telegram")


async def run(owner_id: str, config: dict[str, str] | None = None) -> None:
    """Run the Telegram adapter, reporting status to the registry until cancelled."""
    if config is None:
        config = connector_config.resolve(owner_id, "telegram")
    app = create_app(owner_id, config)
    heartbeat = asyncio.create_task(_heartbeat_loop(owner_id))
    try:
        connector_store.report_status(owner_id, "telegram", "connected")
        await _run_polling(app)
    except asyncio.CancelledError:
        connector_store.report_status(owner_id, "telegram", "stopped")
        raise
    except Exception as exc:
        connector_store.report_status(owner_id, "telegram", "error", error=str(exc))
        raise
    finally:
        heartbeat.cancel()
