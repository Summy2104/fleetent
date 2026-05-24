from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def _derive_session_id(chat_type: str, user_id: int, reply_to_id: int | None) -> str:
    if chat_type == "private":
        return f"user:{user_id}"
    if reply_to_id is not None:
        return f"thread:{reply_to_id}"
    return f"user:{user_id}"


def create_app() -> object:
    """Create and return a configured python-telegram-bot Application."""
    try:
        from telegram.ext import Application
    except ImportError:
        raise RuntimeError("python-telegram-bot not installed") from None

    from mini_agent.config import Settings
    bot_token = Settings().telegram_bot_token
    builder = Application.builder().token(bot_token)
    application = builder.build()

    async def handle_message(update: object, context: object) -> None:
        from telegram import Update

        from mini_agent.im_gateway.normalizer import NormalizedMessage, route  # noqa: PLC0415
        from mini_agent.im_user_store import get_or_create  # noqa: PLC0415

        assert isinstance(update, Update)
        if not update.message or not update.effective_user:
            return

        tg_user_id = update.effective_user.id
        user = get_or_create("telegram", str(tg_user_id))

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
            session_id=session_id,
            user_id=user.id,
            text=update.message.text or "",
            attachments=[],
            reply_func=reply_func,
        )
        await route(msg)

    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
