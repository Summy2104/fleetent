"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI, AsyncStream, RateLimitError
from openai.types.chat import ChatCompletionChunk

import fleetent.tools  # noqa: F401  # side-effect: register built-in tools
from fleetent.agent_policy import check_tool_access
from fleetent.context_mgr import maybe_compress
from fleetent.memory_layer import extract_and_save, load_memories
from fleetent.model_router import RouteConfig, get_async_client_and_config
from fleetent.observability import TraceEvent, record_trace_event
from fleetent.permission_gate import _default_gate
from fleetent.skill_registry import load as load_skill
from fleetent.skill_registry import match as match_skill
from fleetent.skill_registry import scan as scan_skills
from fleetent.sub_agent import SubAgentExecutor
from fleetent.tool_registry import dispatch, get_risk_level, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"


async def _call_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
) -> tuple[Any, str]:
    """Try each model in order on 429/503; return (response, model_used)."""
    last_exc: Exception | None = None
    for model in models:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=cfg.max_tokens,
            )
            return resp, model
        except RateLimitError as exc:
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code == 503:
                last_exc = exc
            else:
                raise
    raise last_exc  # type: ignore[misc]


async def _stream_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
) -> tuple[Any, str]:
    """Try each model in order on 429/503 for streaming; return (stream, model_used)."""
    last_exc: Exception | None = None
    for model in models:
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=cfg.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            return stream, model
        except RateLimitError as exc:
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code == 503:
                last_exc = exc
            else:
                raise
    raise last_exc  # type: ignore[misc]


ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]


def _record_agent_run_completed(
    *,
    user_input: str,
    reply: str,
    messages: list[Any],
    elapsed_s: float,
    usage: Any | None,
    model_used: str,
    user_id: str,
    agent_name: str | None,
) -> None:
    payload: dict[str, Any] = {
        "input": user_input,
        "reply": reply,
        "messages": [_serialize_message(message) for message in messages],
        "elapsed_s": round(elapsed_s, 3),
        "tokens": (
            {
                "prompt": usage.prompt_tokens,
                "completion": usage.completion_tokens,
                "total": usage.total_tokens,
            }
            if usage
            else None
        ),
        "model_used": model_used,
    }
    if agent_name is not None:
        payload["agent_name"] = agent_name
    record_trace_event(
        TraceEvent(
            run_id=str(uuid.uuid4()),
            event_type="agent_run_completed",
            payload=payload,
            user_id=user_id,
            agent_id=agent_name,
        )
    )


def _serialize_message(message: Any) -> Any:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    return str(message)


async def run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    is_sub_agent: bool = False,
    reply_func: ReplyFunc | None = None,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
) -> str:
    """Async agent loop accepting a messages list. Return the final text reply.

    When is_sub_agent=True the sub_agent tool is excluded from the tool schema
    so child agents cannot spawn further sub-agents.
    When allowed_tools is set, only matching tools (fnmatch patterns) are exposed.
    """
    client, cfg = get_async_client_and_config("default")

    # Determine effective tool schemas (exclude sub_agent for child agents)
    schemas = (
        [s for s in get_schemas() if s["function"]["name"] != _SUB_AGENT_TOOL]
        if is_sub_agent
        else get_schemas()
    )

    # Filter by agent-level allowed_tools if specified
    if allowed_tools is not None:
        schemas = [s for s in schemas if check_tool_access(s["function"]["name"], allowed_tools)]

    start = time.monotonic()
    response = None
    msg: Any = None
    models_to_try = [cfg.model, *cfg.fallbacks]
    model_used = cfg.model

    while True:
        messages = maybe_compress(messages)
        response, model_used = await _call_with_fallback(
            client, cfg, messages, schemas, models_to_try
        )
        models_to_try = [model_used]  # stick with the winning model for subsequent turns
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump())  # dict for JSON serializability (session persistence)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            if tc.function.name == _SUB_AGENT_TOOL and not is_sub_agent:
                args = (
                    json.loads(tc.function.arguments)
                    if isinstance(tc.function.arguments, str)
                    else tc.function.arguments
                )
                tasks = (
                    json.loads(args["tasks"])
                    if isinstance(args.get("tasks"), str)
                    else args.get("tasks", [])
                )
                sub_results = await SubAgentExecutor().run(
                    tasks=tasks,
                    parent_user_id=user_id,
                    parent_agent_id=None,
                    parent_session_id="",
                )
                tool_result = "\n".join(
                    f"[{r.name}] {'ERROR: ' + r.error if r.error else r.result}"
                    for r in sub_results
                )
            else:
                risk = get_risk_level(tc.function.name)
                if risk in ("medium", "high") and reply_func is not None:
                    tool_args = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
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
                        tool_result = (
                            f"tool execution {decision}: user did not approve {tc.function.name}"
                        )
                    else:
                        dispatch_result = dispatch(
                            tc.function.name, tc.function.arguments, is_sub_agent=is_sub_agent
                        )
                        tool_result = (
                            dispatch_result
                            if isinstance(dispatch_result, str)
                            else await dispatch_result
                        )
                else:
                    dispatch_result = dispatch(
                        tc.function.name, tc.function.arguments, is_sub_agent=is_sub_agent
                    )
                    tool_result = (
                        dispatch_result
                        if isinstance(dispatch_result, str)
                        else await dispatch_result
                    )
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

    reply = (msg.content if msg is not None else None) or ""
    usage = response.usage if response else None
    user_input = next(
        (m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "user"),
        "",
    )
    _record_agent_run_completed(
        user_input=user_input,
        reply=reply,
        messages=messages,
        elapsed_s=time.monotonic() - start,
        usage=usage,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
    )
    extract_and_save(user_input, messages, user_id=user_id)
    return reply


def run_sync(user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM) -> str:
    """Synchronous wrapper around run() for CLI use."""

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
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
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
    models_to_try = [cfg.model, *cfg.fallbacks]
    model_used = cfg.model
    total_prompt_tokens = 0
    total_completion_tokens = 0

    while True:
        messages = maybe_compress(messages)

        # Accumulate streaming response
        reply_parts: list[str] = []
        # tool_calls_acc: index → {id, name, arguments}
        tool_calls_acc: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        stream_schemas = get_schemas()
        if allowed_tools is not None:
            stream_schemas = [
                s for s in stream_schemas if check_tool_access(s["function"]["name"], allowed_tools)
            ]

        try:
            stream, model_used = await _stream_with_fallback(
                client, cfg, messages, stream_schemas, models_to_try
            )
            models_to_try = [model_used]
        except (RateLimitError, APIStatusError) as exc:
            yield {"type": "error", "content": str(exc)}
            return

        stream = cast(AsyncStream[ChatCompletionChunk], stream)
        async for chunk in stream:
            if chunk.usage:
                total_prompt_tokens += chunk.usage.prompt_tokens
                total_completion_tokens += chunk.usage.completion_tokens
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

    from openai.types import CompletionUsage

    stream_usage: CompletionUsage | None = (
        CompletionUsage(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )
        if total_prompt_tokens or total_completion_tokens
        else None
    )
    _record_agent_run_completed(
        user_input=user_input,
        reply=reply,
        messages=messages,
        elapsed_s=time.monotonic() - start,
        usage=stream_usage,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
    )
    extract_and_save(user_input, messages, user_id=user_id)
