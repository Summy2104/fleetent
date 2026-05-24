"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import time
from collections.abc import AsyncGenerator
from typing import Any, cast

from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk

import asyncio
import inspect
import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import mini_agent.tools  # noqa: F401  # side-effect: register built-in tools
from mini_agent.context_mgr import maybe_compress
from mini_agent.eval_logger import log_run
from mini_agent.memory_layer import extract_and_save, load_memories
from mini_agent.model_router import get_async_client_and_config
from mini_agent.permission_gate import _default_gate
from mini_agent.skill_registry import load as load_skill
from mini_agent.skill_registry import match as match_skill
from mini_agent.skill_registry import scan as scan_skills
from mini_agent.sub_agent import SubAgentExecutor
from mini_agent.tool_registry import dispatch, get_risk_level, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"


ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]


async def run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    is_sub_agent: bool = False,
    reply_func: ReplyFunc | None = None,
) -> str:
    """Async agent loop accepting a messages list. Return the final text reply.

    When is_sub_agent=True the sub_agent tool is excluded from the tool schema
    so child agents cannot spawn further sub-agents.
    """
    client, cfg = get_async_client_and_config("default")

    # Determine effective tool schemas (exclude sub_agent for child agents)
    schemas = [s for s in get_schemas() if s["function"]["name"] != _SUB_AGENT_TOOL] \
        if is_sub_agent else get_schemas()

    start = time.monotonic()
    response = None
    msg: Any = None

    while True:
        messages = maybe_compress(messages)
        response = await client.chat.completions.create(
            model=cfg.model,
            messages=messages,  # type: ignore[arg-type]
            tools=schemas,  # type: ignore[arg-type]
            max_tokens=cfg.max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump())  # dict for JSON serializability (session persistence)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            if tc.function.name == _SUB_AGENT_TOOL and not is_sub_agent:
                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                tasks = json.loads(args["tasks"]) if isinstance(args.get("tasks"), str) else args.get("tasks", [])
                sub_results = await SubAgentExecutor().run(
                    tasks=tasks,
                    parent_user_id=user_id,
                    parent_agent_id=None,
                    parent_session_id="",
                )
                result = "\n".join(
                    f"[{r.name}] {'ERROR: ' + r.error if r.error else r.result}"
                    for r in sub_results
                )
            else:
                risk = get_risk_level(tc.function.name)
                if risk in ("medium", "high") and reply_func is not None:
                    tool_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    approval_id = str(uuid.uuid4())[:8]
                    decision = await _default_gate.request_approval(
                        approval_id=approval_id,
                        risk_level=risk,
                        tool_name=tc.function.name,
                        tool_args=tool_args,
                        requester_user_id=user_id,
                        reply_func=reply_func,
                    )
                    if decision != "approved":
                        result = f"tool execution {decision}: user did not approve {tc.function.name}"
                    else:
                        result = dispatch(tc.function.name, tc.function.arguments, is_sub_agent=is_sub_agent)
                        if inspect.iscoroutine(result):
                            result = await result
                else:
                    result = dispatch(tc.function.name, tc.function.arguments, is_sub_agent=is_sub_agent)
                    if inspect.iscoroutine(result):
                        result = await result
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    reply = (msg.content if msg is not None else None) or ""
    usage = response.usage if response else None
    user_input = next(
        (m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "user"),
        "",
    )
    log_run(user_input, reply, messages, time.monotonic() - start, usage)
    extract_and_save(user_input, messages, user_id=user_id)
    return reply


def run_sync(user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM) -> str:
    """Synchronous wrapper around run() for CLI use."""
    import asyncio

    scan_skills()
    memory_ctx = load_memories(user_id=user_id)
    full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt

    matched = match_skill(user_input)
    if matched:
        skill_content = load_skill(matched)
        full_system = f"{full_system}\n\n{skill_content}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    return asyncio.run(run(messages, user_id=user_id, system_prompt=system_prompt))


async def run_stream(
    user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, done.
    text_delta events stream as tokens arrive from the LLM.
    """
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
    reply = ""

    while True:
        messages = maybe_compress(messages)

        # Accumulate streaming response
        reply_parts: list[str] = []
        # tool_calls_acc: index → {id, name, arguments}
        tool_calls_acc: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        stream = cast(
            AsyncStream[ChatCompletionChunk],
            await client.chat.completions.create(
                model=cfg.model,
                messages=messages,
                tools=get_schemas(),  # type: ignore[arg-type]
                max_tokens=cfg.max_tokens,
                stream=True,
            ),
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                reply_parts.append(delta.content)
                yield {"type": "text_delta", "content": delta.content}

            for tc in delta.tool_calls or []:
                idx = tc.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls_acc[idx]["id"] = tc.id
                if tc.function:
                    tool_calls_acc[idx]["name"] += tc.function.name or ""
                    tool_calls_acc[idx]["arguments"] += tc.function.arguments or ""

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if finish_reason != "tool_calls":
            reply = "".join(reply_parts)
            break

        # Reconstruct assistant message with tool_calls for messages list
        tool_calls_list: list[dict[str, Any]] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in (tool_calls_acc[i] for i in sorted(tool_calls_acc))
        ]
        messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_list})

        # Dispatch tool calls
        for tc_data in tool_calls_list:
            func: dict[str, str] = tc_data["function"]
            name = func["name"]
            args = func["arguments"]
            yield {"type": "tool_call", "name": name, "args": args}
            result = dispatch(name, args)
            yield {"type": "tool_result", "name": name, "content": result}
            messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": result})

    yield {"type": "done", "content": reply}

    log_run(user_input, reply, messages, time.monotonic() - start, usage=None)
    extract_and_save(user_input, messages, user_id=user_id)
