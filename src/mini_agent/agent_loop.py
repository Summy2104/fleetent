"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import time
from collections.abc import AsyncGenerator
from typing import Any

import mini_agent.tools  # noqa: F401  # side-effect: register built-in tools
from mini_agent.context_mgr import maybe_compress
from mini_agent.eval_logger import log_run
from mini_agent.memory_layer import extract_and_save, load_memories
from mini_agent.model_router import get_async_client_and_config, get_client_and_config
from mini_agent.skill_registry import load as load_skill
from mini_agent.skill_registry import match as match_skill
from mini_agent.skill_registry import scan as scan_skills
from mini_agent.tool_registry import dispatch, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."


def run(user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM) -> str:
    """Run the agent loop for a single user turn. Return the final text reply."""
    scan_skills()
    client, cfg = get_client_and_config("default")

    memory_ctx = load_memories(user_id=user_id)
    full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt

    # Inject matching skill into system prompt
    matched = match_skill(user_input)
    if matched:
        skill_content = load_skill(matched)
        full_system = f"{full_system}\n\n{skill_content}"

    messages: list[Any] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    start = time.monotonic()
    response = None

    while True:
        messages = maybe_compress(messages)
        response = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=get_schemas(),  # type: ignore[arg-type]
            max_tokens=cfg.max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            result = dispatch(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    reply = msg.content or ""
    usage = response.usage if response else None
    log_run(user_input, reply, messages, time.monotonic() - start, usage)
    extract_and_save(user_input, messages, user_id=user_id)
    return reply


async def run_stream(
    user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, done.
    """
    scan_skills()
    client, cfg = get_async_client_and_config("default")

    memory_ctx = load_memories(user_id=user_id)
    full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt

    matched = match_skill(user_input)
    if matched:
        full_system = f"{full_system}\n\n{load_skill(matched)}"

    messages: list[Any] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    start = time.monotonic()
    response = None

    while True:
        messages = maybe_compress(messages)
        response = await client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=get_schemas(),  # type: ignore[arg-type]
            max_tokens=cfg.max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            yield {"type": "tool_call", "name": tc.function.name, "args": tc.function.arguments}
            result = dispatch(tc.function.name, tc.function.arguments)
            yield {"type": "tool_result", "name": tc.function.name, "content": result}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    reply = msg.content or ""
    yield {"type": "text_delta", "content": reply}
    yield {"type": "done", "content": reply}

    usage = response.usage if response else None
    log_run(user_input, reply, messages, time.monotonic() - start, usage)
    extract_and_save(user_input, messages, user_id=user_id)
