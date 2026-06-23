"""Telegram heartbeat re-arms the typing action (im-progress-heartbeat)."""

from __future__ import annotations

from fleetent.im_gateway import telegram


class _StubBot:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_chat_action(self, *, chat_id: str, action: str) -> None:
        self.calls.append({"chat_id": chat_id, "action": action})


async def test_heartbeat_event_sends_typing() -> None:
    bot = _StubBot()
    await telegram._send_typing_for_progress(bot, "chat-1", {"type": "heartbeat", "elapsed_s": 5})
    assert bot.calls == [{"chat_id": "chat-1", "action": "typing"}]


async def test_tool_call_event_also_sends_typing() -> None:
    bot = _StubBot()
    await telegram._send_typing_for_progress(bot, "chat-1", {"type": "tool_call", "names": ["x"]})
    assert bot.calls == [{"chat_id": "chat-1", "action": "typing"}]


async def test_typing_failure_is_swallowed() -> None:
    class _Boom:
        async def send_chat_action(self, **kw):
            raise RuntimeError("network")

    # must not raise
    evt = {"type": "heartbeat", "elapsed_s": 1}
    await telegram._send_typing_for_progress(_Boom(), "chat-1", evt)
