from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."


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
    from mini_agent.memory_layer import load_memories
    from mini_agent.skill_registry import load as load_skill
    from mini_agent.skill_registry import match as match_skill

    async with session_mgr.session_lock(msg.session_id):
        history = await session_mgr.load(msg.session_id)

        # Build fresh system message: memories + matching skill
        memory_ctx = load_memories(user_id=msg.user_id)
        system_content = f"{memory_ctx}\n\n{_SYSTEM}" if memory_ctx else _SYSTEM
        matched = match_skill(msg.text)
        if matched:
            system_content = f"{system_content}\n\n{load_skill(matched)}"

        # Replace existing system message or insert at position 0
        if history and isinstance(history[0], dict) and history[0].get("role") == "system":
            history[0]["content"] = system_content
        else:
            history.insert(0, {"role": "system", "content": system_content})

        history.append({"role": "user", "content": msg.text})

        response = await agent_loop.run(messages=history, user_id=msg.user_id, reply_func=msg.reply_func)

        # agent_loop.run() already appended the assistant message to history in-place.
        # Do NOT append again here — that caused duplicate messages in every session.
        await session_mgr.save(msg.session_id, history)

    await msg.reply_func(response)
