"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, Literal, cast

from openai import APIStatusError, AsyncOpenAI, AsyncStream, RateLimitError
from openai.types.chat import ChatCompletionChunk

import fleetent.tools  # noqa: F401  # side-effect: register built-in tools
from fleetent.agent_runtime import AgentSnapshot, filter_tool_schemas
from fleetent.context_mgr import maybe_compress
from fleetent.governance.permission_gate import _default_gate
from fleetent.intelligence.long_term_ctx import ContextSource, build_context
from fleetent.model_router import RouteConfig, get_async_client_and_config
from fleetent.observability import (
    InjectedContextTrace,
    TraceEvent,
    record_injected_context,
    record_trace_event,
)
from fleetent.skill_registry import SkillIndex
from fleetent.skill_registry import load as load_skill
from fleetent.skill_registry import match as match_skill
from fleetent.skill_registry import scan as scan_skills
from fleetent.sub_agent import SubAgentExecutor
from fleetent.tool_registry import dispatch, get_risk_level, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"
_INVOKE_AGENT_TOOL = "invoke_agent"
# Tools a child agent must not see: it can neither spawn sub-agents nor delegate
# to another named agent (depth is capped at 1).
_SUB_AGENT_EXCLUDED_TOOLS = frozenset({_SUB_AGENT_TOOL, _INVOKE_AGENT_TOOL})
_LONG_TERM_CONTEXT_HEADER = "[Long-term context]"


async def _call_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
    *,
    run_id: str,
    user_id: str,
    agent_name: str | None,
) -> tuple[Any, str]:
    """Try each model in order on 429/503; return (response, model_used)."""
    last_exc: Exception | None = None
    for index, model in enumerate(models):
        attempt_start = time.monotonic()
        _record_llm_call_started(
            run_id=run_id,
            model=model,
            messages=messages,
            schemas=schemas,
            streaming=False,
            user_id=user_id,
            agent_name=agent_name,
        )
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=cfg.max_tokens,
            )
            _record_llm_call_completed(
                run_id=run_id,
                model=model,
                finish_reason=resp.choices[0].finish_reason if resp.choices else None,
                usage=getattr(resp, "usage", None),
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            return resp, model
        except RateLimitError as exc:
            _record_llm_call_failed(
                run_id=run_id,
                model=model,
                exc=exc,
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code == 503:
                _record_llm_call_failed(
                    run_id=run_id,
                    model=model,
                    exc=exc,
                    elapsed_s=time.monotonic() - attempt_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                last_exc = exc
            else:
                _record_llm_call_failed(
                    run_id=run_id,
                    model=model,
                    exc=exc,
                    elapsed_s=time.monotonic() - attempt_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                raise
        except Exception as exc:
            _record_llm_call_failed(
                run_id=run_id,
                model=model,
                exc=exc,
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            raise
        if index + 1 < len(models):
            _record_model_fallback_triggered(
                run_id=run_id,
                from_model=model,
                to_model=models[index + 1],
                reason=last_exc,
                attempt_index=index + 1,
                user_id=user_id,
                agent_name=agent_name,
            )
    raise last_exc  # type: ignore[misc]


async def _stream_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
    *,
    run_id: str,
    user_id: str,
    agent_name: str | None,
) -> tuple[Any, str]:
    """Try each model in order on 429/503 for streaming; return (stream, model_used)."""
    last_exc: Exception | None = None
    for index, model in enumerate(models):
        attempt_start = time.monotonic()
        _record_llm_call_started(
            run_id=run_id,
            model=model,
            messages=messages,
            schemas=schemas,
            streaming=True,
            user_id=user_id,
            agent_name=agent_name,
        )
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=cfg.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            _record_llm_call_completed(
                run_id=run_id,
                model=model,
                finish_reason=None,
                usage=None,
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            return stream, model
        except RateLimitError as exc:
            _record_llm_call_failed(
                run_id=run_id,
                model=model,
                exc=exc,
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code == 503:
                _record_llm_call_failed(
                    run_id=run_id,
                    model=model,
                    exc=exc,
                    elapsed_s=time.monotonic() - attempt_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                last_exc = exc
            else:
                _record_llm_call_failed(
                    run_id=run_id,
                    model=model,
                    exc=exc,
                    elapsed_s=time.monotonic() - attempt_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                raise
        except Exception as exc:
            _record_llm_call_failed(
                run_id=run_id,
                model=model,
                exc=exc,
                elapsed_s=time.monotonic() - attempt_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            raise
        if index + 1 < len(models):
            _record_model_fallback_triggered(
                run_id=run_id,
                from_model=model,
                to_model=models[index + 1],
                reason=last_exc,
                attempt_index=index + 1,
                user_id=user_id,
                agent_name=agent_name,
            )
    raise last_exc  # type: ignore[misc]


ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]


def _record_runtime_event(
    *,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    user_id: str,
    agent_name: str | None,
) -> None:
    record_trace_event(
        TraceEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            user_id=user_id,
            agent_id=agent_name,
        )
    )


def _record_agent_run_started(
    *,
    run_id: str,
    user_id: str,
    agent_name: str | None,
    entrypoint: Literal["run", "run_stream"],
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "entrypoint": entrypoint,
    }
    if agent_name is not None:
        payload["agent_name"] = agent_name
    _record_runtime_event(
        run_id=run_id,
        event_type="agent_run_started",
        payload=payload,
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_agent_run_failed(
    *,
    run_id: str,
    exc: Exception,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
    entrypoint: Literal["run", "run_stream"],
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="agent_run_failed",
        payload={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "elapsed_s": round(elapsed_s, 3),
            "entrypoint": entrypoint,
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_llm_call_started(
    *,
    run_id: str,
    model: str,
    messages: list[Any],
    schemas: list[Any],
    streaming: bool,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="llm_call_started",
        payload={
            "model": model,
            "task_type": "default",
            "streaming": streaming,
            "message_count": len(messages),
            "tool_schema_count": len(schemas),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_llm_call_completed(
    *,
    run_id: str,
    model: str,
    finish_reason: str | None,
    usage: Any | None,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    payload: dict[str, Any] = {
        "model": model,
        "finish_reason": finish_reason,
        "elapsed_s": round(elapsed_s, 3),
    }
    tokens = _token_usage_payload(usage)
    if tokens is not None:
        payload["tokens"] = tokens
    _record_runtime_event(
        run_id=run_id,
        event_type="llm_call_completed",
        payload=payload,
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_llm_call_failed(
    *,
    run_id: str,
    model: str,
    exc: Exception,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="llm_call_failed",
        payload={
            "model": model,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "elapsed_s": round(elapsed_s, 3),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_model_fallback_triggered(
    *,
    run_id: str,
    from_model: str,
    to_model: str,
    reason: Exception | None,
    attempt_index: int,
    user_id: str,
    agent_name: str | None,
) -> None:
    reason_text = ""
    if reason is not None:
        reason_text = f"{type(reason).__name__}: {reason}"
    _record_runtime_event(
        run_id=run_id,
        event_type="model_fallback_triggered",
        payload={
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason_text,
            "attempt_index": attempt_index,
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _token_usage_payload(usage: Any | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "prompt": usage.prompt_tokens,
        "completion": usage.completion_tokens,
        "total": usage.total_tokens,
    }


def _record_tool_call_started(
    *,
    run_id: str,
    tool_name: str,
    tool_call_id: str,
    risk_level: str,
    arguments: Any,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="tool_call_started",
        payload={
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "risk_level": risk_level,
            "argument_summary": _argument_summary(arguments),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_tool_call_completed(
    *,
    run_id: str,
    tool_name: str,
    tool_call_id: str,
    result: Any,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="tool_call_completed",
        payload={
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "elapsed_s": round(elapsed_s, 3),
            "result_summary": _result_summary(result),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_tool_call_failed(
    *,
    run_id: str,
    tool_name: str,
    tool_call_id: str,
    exc: Exception,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="tool_call_failed",
        payload={
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "elapsed_s": round(elapsed_s, 3),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_permission_requested(
    *,
    run_id: str,
    approval_id: str,
    tool_name: str,
    risk_level: str,
    requester_user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="permission_requested",
        payload={
            "approval_id": approval_id,
            "tool_name": tool_name,
            "risk_level": risk_level,
            "requester_user_id": requester_user_id,
        },
        user_id=requester_user_id,
        agent_name=agent_name,
    )


def _record_permission_resolved(
    *,
    run_id: str,
    approval_id: str,
    tool_name: str,
    risk_level: str,
    decision: str,
    elapsed_s: float,
    requester_user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="permission_resolved",
        payload={
            "approval_id": approval_id,
            "tool_name": tool_name,
            "risk_level": risk_level,
            "decision": decision,
            "elapsed_s": round(elapsed_s, 3),
        },
        user_id=requester_user_id,
        agent_name=agent_name,
    )


def _record_context_compression_completed(
    *,
    run_id: str,
    before_message_count: int,
    after_message_count: int,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="context_compression_completed",
        payload={
            "reason": "runtime_message_compression",
            "before_message_count": before_message_count,
            "after_message_count": after_message_count,
            "elapsed_s": round(elapsed_s, 3),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _record_final_reply_emitted(
    *,
    run_id: str,
    reply: str,
    elapsed_s: float,
    user_id: str,
    agent_name: str | None,
) -> None:
    _record_runtime_event(
        run_id=run_id,
        event_type="final_reply_emitted",
        payload={
            "reply_length": len(reply),
            "elapsed_s": round(elapsed_s, 3),
        },
        user_id=user_id,
        agent_name=agent_name,
    )


def _maybe_compress_with_trace(
    *,
    run_id: str,
    messages: list[Any],
    user_id: str,
    agent_name: str | None,
) -> list[Any]:
    before_count = len(messages)
    compression_start = time.monotonic()
    compressed = maybe_compress(messages)
    if compressed is not messages and compressed != messages:
        _record_context_compression_completed(
            run_id=run_id,
            before_message_count=before_count,
            after_message_count=len(compressed),
            elapsed_s=time.monotonic() - compression_start,
            user_id=user_id,
            agent_name=agent_name,
        )
    return compressed


def _argument_summary(arguments: Any) -> dict[str, Any]:
    parsed = _parse_json_if_string(arguments)
    if isinstance(parsed, dict):
        return {
            "type": "object",
            "keys": sorted(str(key) for key in parsed),
            "field_count": len(parsed),
            "truncated": False,
        }
    if isinstance(parsed, list):
        return {"type": "array", "item_count": len(parsed), "truncated": False}
    value = "" if parsed is None else str(parsed)
    return {"type": type(parsed).__name__, "length": len(value), "truncated": False}


def _result_summary(result: Any) -> dict[str, Any]:
    value = "" if result is None else str(result)
    return {"type": type(result).__name__, "length": len(value), "truncated": False}


def _parse_json_if_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _record_agent_run_completed(
    *,
    run_id: str,
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
            run_id=run_id,
            event_type="agent_run_completed",
            payload=payload,
            user_id=user_id,
            agent_id=agent_name,
        )
    )


def _record_injected_context(run_id: str, sources: list[ContextSource]) -> None:
    if not sources:
        return
    record_injected_context(
        run_id,
        [
            InjectedContextTrace(
                source_id=source.source_id,
                source_type=cast(Literal["memory", "knowledge"], source.source_type),
                score=source.score,
                token_estimate=int(getattr(source, "token_estimate", 0)),
                metadata=source.metadata,
            )
            for source in sources
        ],
    )


def _serialize_message(message: Any) -> Any:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    return str(message)


def _first_user_content(messages: list[Any]) -> str:
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def _append_system_context(messages: list[Any], system_prompt: str, context_text: str) -> None:
    if not context_text:
        return
    addition = f"{_LONG_TERM_CONTEXT_HEADER}\n{context_text}"
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "system":
            message["content"] = f"{message.get('content', '')}\n\n{addition}"
            return
    messages.insert(0, {"role": "system", "content": f"{system_prompt}\n\n{addition}"})


async def run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    is_sub_agent: bool = False,
    reply_func: ReplyFunc | None = None,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
    snapshot: AgentSnapshot | None = None,
) -> str:
    """Async agent loop accepting a messages list. Return the final text reply.

    When is_sub_agent=True the sub_agent tool is excluded from the tool schema
    so child agents cannot spawn further sub-agents.
    When a ``snapshot`` is given its per-agent config (allowed_tools, MCP
    whitelist, model overrides, memory namespace) is applied; otherwise the
    loop falls back to the global behaviour (and the legacy ``allowed_tools``).
    """
    eff_allowed = snapshot.allowed_tools if snapshot is not None else allowed_tools
    mcp_server_ids = snapshot.mcp_server_ids if snapshot is not None else None
    overrides = snapshot.model_overrides if snapshot is not None else None
    memory_namespace = snapshot.memory_namespace if snapshot is not None else "default"
    if snapshot is not None:
        agent_name = agent_name or snapshot.name

    client, cfg = get_async_client_and_config("default", overrides=overrides)
    run_id = str(uuid.uuid4())
    start = time.monotonic()
    _record_agent_run_started(
        run_id=run_id,
        user_id=user_id,
        agent_name=agent_name,
        entrypoint="run",
    )
    user_input = _first_user_content(messages)
    try:
        built_context = await build_context(
            user_id, user_input, agent_name or "", cfg.max_tokens, memory_namespace=memory_namespace
        )
        _append_system_context(messages, system_prompt, built_context.text)
        _record_injected_context(run_id, built_context.sources)

        # Determine effective tool schemas (child agents cannot delegate further)
        schemas = (
            [s for s in get_schemas() if s["function"]["name"] not in _SUB_AGENT_EXCLUDED_TOOLS]
            if is_sub_agent
            else get_schemas()
        )
        schemas = filter_tool_schemas(schemas, eff_allowed, mcp_server_ids)

        response = None
        msg: Any = None
        models_to_try = [cfg.model, *cfg.fallbacks]
        model_used = cfg.model

        while True:
            messages = _maybe_compress_with_trace(
                run_id=run_id,
                messages=messages,
                user_id=user_id,
                agent_name=agent_name,
            )
            response, model_used = await _call_with_fallback(
                client,
                cfg,
                messages,
                schemas,
                models_to_try,
                run_id=run_id,
                user_id=user_id,
                agent_name=agent_name,
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
                tool_name = tc.function.name
                tool_call_id = tc.id
                risk = get_risk_level(tool_name)
                tool_start = time.monotonic()
                _record_tool_call_started(
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    risk_level=risk,
                    arguments=tc.function.arguments,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                try:
                    if tool_name == _SUB_AGENT_TOOL and not is_sub_agent:
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
                        if risk in ("medium", "high") and reply_func is not None:
                            tool_args = (
                                json.loads(tc.function.arguments)
                                if isinstance(tc.function.arguments, str)
                                else tc.function.arguments
                            )
                            approval_id = str(uuid.uuid4())[:8]
                            approval_start = time.monotonic()
                            _record_permission_requested(
                                run_id=run_id,
                                approval_id=approval_id,
                                tool_name=tool_name,
                                risk_level=risk,
                                requester_user_id=user_id,
                                agent_name=agent_name,
                            )
                            decision = await _default_gate.request_approval(
                                approval_id=approval_id,
                                risk_level=risk,
                                tool_name=tool_name,
                                tool_args=tool_args,
                                requester_user_id=user_id,
                                reply_func=reply_func,
                            )
                            _record_permission_resolved(
                                run_id=run_id,
                                approval_id=approval_id,
                                tool_name=tool_name,
                                risk_level=risk,
                                decision=decision,
                                elapsed_s=time.monotonic() - approval_start,
                                requester_user_id=user_id,
                                agent_name=agent_name,
                            )
                            if decision != "approved":
                                tool_result = (
                                    f"tool execution {decision}: user did not approve {tool_name}"
                                )
                            else:
                                dispatch_result = dispatch(
                                    tool_name,
                                    tc.function.arguments,
                                    is_sub_agent=is_sub_agent,
                                )
                                tool_result = (
                                    dispatch_result
                                    if isinstance(dispatch_result, str)
                                    else await dispatch_result
                                )
                        else:
                            dispatch_result = dispatch(
                                tool_name, tc.function.arguments, is_sub_agent=is_sub_agent
                            )
                            tool_result = (
                                dispatch_result
                                if isinstance(dispatch_result, str)
                                else await dispatch_result
                            )
                except Exception as exc:
                    _record_tool_call_failed(
                        run_id=run_id,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        exc=exc,
                        elapsed_s=time.monotonic() - tool_start,
                        user_id=user_id,
                        agent_name=agent_name,
                    )
                    raise
                _record_tool_call_completed(
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    result=tool_result,
                    elapsed_s=time.monotonic() - tool_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call_id, "content": tool_result}
                )

        reply = (msg.content if msg is not None else None) or ""
        usage = response.usage if response else None
        user_input = next(
            (m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "user"),
            "",
        )
        elapsed_s = time.monotonic() - start
        _record_final_reply_emitted(
            run_id=run_id,
            reply=reply,
            elapsed_s=elapsed_s,
            user_id=user_id,
            agent_name=agent_name,
        )
        _record_agent_run_completed(
            run_id=run_id,
            user_input=user_input,
            reply=reply,
            messages=messages,
            elapsed_s=elapsed_s,
            usage=usage,
            model_used=model_used,
            user_id=user_id,
            agent_name=agent_name,
        )
        return reply
    except Exception as exc:
        _record_agent_run_failed(
            run_id=run_id,
            exc=exc,
            elapsed_s=time.monotonic() - start,
            user_id=user_id,
            agent_name=agent_name,
            entrypoint="run",
        )
        raise


def _match_skill_for(user_input: str, snapshot: AgentSnapshot | None) -> str | None:
    """Return the matched skill body, scoped to the snapshot's skills dir if set."""
    if snapshot is not None and snapshot.skills_dir:
        index = SkillIndex(snapshot.skills_dir)
        name = index.match(user_input)
        return index.load(name) if name else None
    name = match_skill(user_input)
    return load_skill(name) if name else None


def run_sync(
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    snapshot: AgentSnapshot | None = None,
) -> str:
    """Synchronous wrapper around run() for CLI use."""

    scan_skills()
    full_system = system_prompt

    matched = _match_skill_for(user_input, snapshot)
    if matched is not None:
        full_system = f"{full_system}\n\n{matched}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    return asyncio.run(
        run(messages, user_id=user_id, system_prompt=system_prompt, snapshot=snapshot)
    )


async def run_stream(
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
    snapshot: AgentSnapshot | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, done.
    text_delta events stream as tokens arrive from the LLM.
    When a ``snapshot`` is given its per-agent config (skills dir, allowed_tools,
    MCP whitelist, model overrides, memory namespace) is applied.
    """
    eff_allowed = snapshot.allowed_tools if snapshot is not None else allowed_tools
    mcp_server_ids = snapshot.mcp_server_ids if snapshot is not None else None
    overrides = snapshot.model_overrides if snapshot is not None else None
    memory_namespace = snapshot.memory_namespace if snapshot is not None else "default"
    if snapshot is not None:
        agent_name = agent_name or snapshot.name

    client, cfg = get_async_client_and_config("default", overrides=overrides)
    run_id = str(uuid.uuid4())
    start = time.monotonic()
    _record_agent_run_started(
        run_id=run_id,
        user_id=user_id,
        agent_name=agent_name,
        entrypoint="run_stream",
    )

    full_system = system_prompt

    matched = _match_skill_for(user_input, snapshot)
    if matched is not None:
        full_system = f"{full_system}\n\n{matched}"

    messages: list[Any] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]
    built_context = await build_context(
        user_id, user_input, agent_name or "", cfg.max_tokens, memory_namespace=memory_namespace
    )
    _append_system_context(messages, full_system, built_context.text)
    _record_injected_context(run_id, built_context.sources)

    reply = ""
    models_to_try = [cfg.model, *cfg.fallbacks]
    model_used = cfg.model
    total_prompt_tokens = 0
    total_completion_tokens = 0

    while True:
        messages = _maybe_compress_with_trace(
            run_id=run_id,
            messages=messages,
            user_id=user_id,
            agent_name=agent_name,
        )

        # Accumulate streaming response
        reply_parts: list[str] = []
        # tool_calls_acc: index → {id, name, arguments}
        tool_calls_acc: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        stream_schemas = filter_tool_schemas(get_schemas(), eff_allowed, mcp_server_ids)

        try:
            stream, model_used = await _stream_with_fallback(
                client,
                cfg,
                messages,
                stream_schemas,
                models_to_try,
                run_id=run_id,
                user_id=user_id,
                agent_name=agent_name,
            )
            models_to_try = [model_used]
        except (RateLimitError, APIStatusError) as exc:
            _record_agent_run_failed(
                run_id=run_id,
                exc=exc,
                elapsed_s=time.monotonic() - start,
                user_id=user_id,
                agent_name=agent_name,
                entrypoint="run_stream",
            )
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
            tool_start = time.monotonic()
            risk = get_risk_level(name)
            _record_tool_call_started(
                run_id=run_id,
                tool_name=name,
                tool_call_id=tc_data["id"],
                risk_level=risk,
                arguments=args,
                user_id=user_id,
                agent_name=agent_name,
            )
            yield {"type": "tool_call", "name": name, "args": args}
            try:
                result = dispatch(name, args)
            except Exception as exc:
                _record_tool_call_failed(
                    run_id=run_id,
                    tool_name=name,
                    tool_call_id=tc_data["id"],
                    exc=exc,
                    elapsed_s=time.monotonic() - tool_start,
                    user_id=user_id,
                    agent_name=agent_name,
                )
                raise
            _record_tool_call_completed(
                run_id=run_id,
                tool_name=name,
                tool_call_id=tc_data["id"],
                result=result,
                elapsed_s=time.monotonic() - tool_start,
                user_id=user_id,
                agent_name=agent_name,
            )
            yield {"type": "tool_result", "name": name, "content": result}
            messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": result})

    elapsed_s = time.monotonic() - start
    _record_final_reply_emitted(
        run_id=run_id,
        reply=reply,
        elapsed_s=elapsed_s,
        user_id=user_id,
        agent_name=agent_name,
    )
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
        run_id=run_id,
        user_input=user_input,
        reply=reply,
        messages=messages,
        elapsed_s=elapsed_s,
        usage=stream_usage,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
    )
