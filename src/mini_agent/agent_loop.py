"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import time
from typing import Any

import mini_agent.tools  # noqa: F401  # side-effect: register built-in tools
from mini_agent.eval_logger import log_run
from mini_agent.model_router import get_client_and_config
from mini_agent.tool_registry import dispatch, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."


def run(user_input: str, system_prompt: str = _SYSTEM) -> str:
    """Run the agent loop for a single user turn. Return the final text reply."""
    client, cfg = get_client_and_config("default")

    messages: list[Any] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    start = time.monotonic()
    response = None

    while True:
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
    return reply
