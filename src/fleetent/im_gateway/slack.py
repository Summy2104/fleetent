from __future__ import annotations

import asyncio

import structlog

from fleetent.platform.im_gateway_management import connector_config, connector_store

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0


def _derive_session_id(user_id: str, channel_type: str, thread_ts: str | None) -> str:
    if channel_type == "im":
        return f"user:{user_id}"
    if thread_ts:
        return f"thread:{thread_ts}"
    # Channel message without thread: use user as session (bot will reply in thread)
    return f"user:{user_id}"


def create_app(owner_id: str, config: dict[str, str]) -> object:
    """Create and return a configured slack-bolt AsyncApp with Socket Mode."""
    try:
        from slack_bolt.async_app import AsyncApp
    except ImportError:
        raise RuntimeError("slack-bolt not installed") from None

    app = AsyncApp(token=config.get("bot_token", ""))

    @app.event("message")
    async def handle_message(event: dict[str, str | None], say: object) -> None:
        from fleetent.im_gateway.normalizer import NormalizedMessage, route
        from fleetent.platform.im_gateway_management.identity import get_or_create

        slack_user_id = event.get("user") or "unknown"
        user = get_or_create(owner_id, "slack", slack_user_id)
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
            owner_id=owner_id,
            session_id=session_id,
            user_id=user.id,
            text=event.get("text") or "",
            attachments=[],
            reply_func=reply_func,
            channel_id=event.get("channel") or "",
        )
        await route(msg)

    return app


async def _run_socket_mode(app: object, app_token: str) -> None:
    """Open the Socket Mode connection and serve until cancelled (network seam)."""
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    handler = AsyncSocketModeHandler(app, app_token)  # type: ignore[arg-type]
    await handler.start_async()  # type: ignore[no-untyped-call]


async def _heartbeat_loop(owner_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        connector_store.heartbeat(owner_id, "slack")


async def run(owner_id: str, config: dict[str, str] | None = None) -> None:
    """Run the Slack adapter, reporting status to the registry until cancelled."""
    if config is None:
        config = connector_config.resolve(owner_id, "slack")
    app = create_app(owner_id, config)
    heartbeat = asyncio.create_task(_heartbeat_loop(owner_id))
    try:
        connector_store.report_status(owner_id, "slack", "connected")
        await _run_socket_mode(app, config.get("app_token", ""))
    except asyncio.CancelledError:
        connector_store.report_status(owner_id, "slack", "stopped")
        raise
    except Exception as exc:
        connector_store.report_status(owner_id, "slack", "error", error=str(exc))
        raise
    finally:
        heartbeat.cancel()
