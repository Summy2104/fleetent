from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def _derive_session_id(user_id: str, channel_type: str, thread_ts: str | None) -> str:
    if channel_type == "im":
        return f"user:{user_id}"
    if thread_ts:
        return f"thread:{thread_ts}"
    # Channel message without thread: use user as session (bot will reply in thread)
    return f"user:{user_id}"


def create_app() -> object:
    """Create and return a configured slack-bolt AsyncApp with Socket Mode."""
    try:
        from slack_bolt.async_app import AsyncApp
    except ImportError:
        raise RuntimeError("slack-bolt not installed") from None

    from fleetent.config import Settings

    bot_token = Settings().slack_bot_token  # type: ignore[call-arg]
    app = AsyncApp(token=bot_token)

    @app.event("message")
    async def handle_message(event: dict[str, str | None], say: object) -> None:
        from fleetent.im_gateway.normalizer import NormalizedMessage, route
        from fleetent.im_user_store import get_or_create

        slack_user_id = event.get("user") or "unknown"
        user = get_or_create("slack", slack_user_id)
        thread_ts = event.get("thread_ts")
        channel_type = event.get("channel_type") or "channel"

        session_id = _derive_session_id(
            user_id=slack_user_id,
            channel_type=channel_type,
            thread_ts=thread_ts,
        )

        reply_thread = thread_ts or event.get("ts")

        async def reply_func(text: str) -> None:
            await say(text=text, thread_ts=reply_thread)  # type: ignore[operator]

        msg = NormalizedMessage(
            platform="slack",
            session_id=session_id,
            user_id=user.id,
            text=event.get("text") or "",
            attachments=[],
            reply_func=reply_func,
        )
        await route(msg)

    return app
