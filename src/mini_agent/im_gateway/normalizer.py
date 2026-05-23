from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class NormalizedMessage:
    platform: str
    session_id: str
    user_id: str
    text: str
    attachments: list[Any]
    reply_func: Callable[[str], Coroutine[Any, Any, None]]


async def route(msg: NormalizedMessage) -> None:
    from mini_agent import agent_loop, session_mgr

    async with session_mgr.session_lock(msg.session_id):
        history = await session_mgr.load(msg.session_id)
        history.append({"role": "user", "content": msg.text})

        response = await agent_loop.run(
            messages=history,
            user_id=msg.user_id,
        )

        history.append({"role": "assistant", "content": response})
        await session_mgr.save(msg.session_id, history)

    await msg.reply_func(response)
