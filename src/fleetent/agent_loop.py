"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import asyncio
import inspect
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI, AsyncStream, RateLimitError
from openai.types.chat import ChatCompletionChunk

import fleetent.tools  # noqa: F401  # side-effect: register built-in tools
from fleetent import model_router
from fleetent.agent_policy import check_tool_access
from fleetent.context_mgr import maybe_compress
from fleetent.error_classifier import classify
from fleetent.eval_logger import log_run
from fleetent.loop_detector import LoopDetectionChecker, arg_fingerprint, result_digest
from fleetent.memory_layer import extract_and_save, load_memories
from fleetent.message_hygiene import HygieneReport, MessageContractError, sanitize
from fleetent.model_router import RouteConfig, RouteOverride, get_async_client_and_config
from fleetent.multimodal import build_message_with_images, has_image_block
from fleetent.permission_gate import _default_gate
from fleetent.provider_health import ProviderHealthCache, get_health_cache
from fleetent.skill_registry import available_skills_prompt, collect_disabled_trace
from fleetent.skill_registry import scan as scan_skills
from fleetent.sub_agent import SubAgentExecutor
from fleetent.termination import (
    ApprovalRejectedChecker,
    ConsecutiveFailuresChecker,
    LoopState,
    MaxTurnsChecker,
    StopReason,
    TerminationController,
    resolve_limits,
)
from fleetent.tool_registry import dispatch, get_risk_level, get_schemas

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"

# Corrective warning injected when the loop-detection checker first flags a
# suspected loop (AR4 D3/D4). Plain `user` role (D4) so it is not merged with the
# leading system prompt by message_hygiene and stays visible on the next turn.
_LOOP_WARNING_TEXT = (
    "检测到你正在重复调用同一工具且似乎没有进展，请改用其它方式或直接给出当前结论。"
)


def _resolve_loop_config(
    repeat_threshold: int | None,
    ignore_arg_keys: list[str] | None,
) -> tuple[int, list[str]]:
    """Resolve loop-detection settings: call param > Settings > default (D3)."""
    if repeat_threshold is not None and ignore_arg_keys is not None:
        return repeat_threshold, ignore_arg_keys
    from fleetent.config import Settings

    s = Settings()
    return (
        repeat_threshold if repeat_threshold is not None else s.agent_loop_repeat_threshold,
        ignore_arg_keys if ignore_arg_keys is not None else list(s.loop_detect_ignore_arg_keys),
    )


def _build_controller(
    max_turns: int | None,
    max_consecutive_failures: int | None,
    *,
    include_approval: bool,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
) -> tuple[TerminationController, LoopDetectionChecker]:
    """Assemble the termination controller with the active checkers.

    The loop-detection checker (AR4) registers AFTER the existing checkers so the
    established termination priority (max_turns / consecutive_failures /
    approval_rejected) is unchanged. Returns the checker too so the loop can read
    its derived history window.
    """
    mt, mcf = resolve_limits(max_turns, max_consecutive_failures)
    threshold, ignore_keys = _resolve_loop_config(loop_repeat_threshold, loop_ignore_arg_keys)
    controller = TerminationController()
    controller.register(MaxTurnsChecker(mt))
    controller.register(ConsecutiveFailuresChecker(mcf))
    if include_approval:
        controller.register(ApprovalRejectedChecker())
    loop_checker = LoopDetectionChecker(threshold, ignore_keys)
    controller.register(loop_checker)
    return controller, loop_checker


def _maybe_inject_loop_warning(messages: list[Any], state: LoopState) -> None:
    """Append the corrective warning when the checker requested it (D3/D4/D4b).

    Called right before the next LLM call (after any compression this round) so a
    same-round `maybe_compress` cannot swallow the warning. Idempotent within a run:
    once injected, `loop_warning_injected` gates re-injection.
    """
    if state.loop_warning_requested and not state.loop_warning_injected:
        messages.append({"role": "user", "content": _LOOP_WARNING_TEXT})
        state.loop_warning_injected = True


async def _safe_dispatch(
    name: str, arguments: str | dict[str, Any], is_sub_agent: bool
) -> tuple[str, bool]:
    """Dispatch a tool, normalizing a crash into (error_text, failed=True).

    Returning instead of raising keeps a tool crash from killing the loop and
    lets the consecutive-failures checker observe it.
    """
    try:
        result = dispatch(name, arguments, is_sub_agent=is_sub_agent)
        if inspect.iscoroutine(result):
            result = await result
        return result, False
    except Exception as exc:  # normalized for the loop; not swallowed silently
        return f"tool execution error: {exc}", True


def _candidates(models: list[str], cache: ProviderHealthCache) -> list[str]:
    """Models to actually try, skipping those in cooldown (MR3, design D4).

    When every candidate is cooling we fall back to the full original list rather
    than skip all of them: probing the cooling providers preserves the existing
    "providers exhausted → raise" contract instead of silently returning nothing.
    """
    available = [m for m in models if cache.is_available(m)]
    return available or models


async def _call_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
) -> tuple[Any, str]:
    """Try each model in order on 429/503; return (response, model_used).

    Providers currently in cooldown (per the health cache, MR3) are skipped so a
    known-bad provider no longer costs its timeout on every request. A successful
    call closes that provider's breaker; a switchable failure records against it.
    """
    cache = get_health_cache()
    last_exc: Exception | None = None
    for model in _candidates(models, cache):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=schemas,  # type: ignore[arg-type]
                max_tokens=cfg.max_tokens,
                **cfg.params,
            )
            cache.record_success(model)
            return resp, model
        except Exception as exc:
            # Classification owns the "should we switch models?" decision; the
            # loop no longer hardcodes status codes here (design D5). Only a
            # switchable failure (429/503) counts against the provider's breaker.
            if not classify(exc).should_switch_model:
                raise
            cache.record_failure(model)
            last_exc = exc
    raise last_exc  # type: ignore[misc]


async def _stream_with_fallback(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
) -> tuple[Any, str]:
    """Try each model in order on 429/503 for streaming; return (stream, model_used).

    Shares the health cache with `_call_with_fallback`: cooling providers are
    skipped, successes close the breaker, switchable failures record against it.
    """
    cache = get_health_cache()
    last_exc: Exception | None = None
    for model in _candidates(models, cache):
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=schemas,  # type: ignore[arg-type]
                max_tokens=cfg.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                **cfg.params,
            )
            cache.record_success(model)
            return stream, model
        except Exception as exc:
            if not classify(exc).should_switch_model:
                raise
            cache.record_failure(model)
            last_exc = exc
    raise last_exc  # type: ignore[misc]


def _content_to_text(content: Any) -> str:
    """Reduce a message content to text: str passes through; block arrays keep
    only their text blocks (AR21 — never stringify base64 image blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b["text"]
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        )
    return ""


def _first_user_input(messages: list[Any]) -> str:
    return next(
        (
            _content_to_text(m.get("content"))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ),
        "",
    )


def _select_route(messages: list[Any]) -> str:
    """Pick the task_type for this run: vision when an image block is present.

    Raises when images are present but no `vision` route is configured (D6,
    option A) so the loop fails locally rather than sending an image to a
    non-vision model.
    """
    if not has_image_block(messages):
        return "default"
    if "vision" not in model_router.ROUTES:
        raise RuntimeError(
            "消息含图片但未配置 vision 路由（model_router.ROUTES 缺少 'vision'），无法处理图片输入"
        )
    return "vision"


def _log_run_error(
    exc: Exception,
    messages: list[Any],
    start: float,
    model_used: str,
    user_id: str | None,
    agent_name: str | None,
) -> None:
    """Write a trace record tagged with the error's classification code."""
    log_run(
        _first_user_input(messages),
        "",
        messages,
        time.monotonic() - start,
        None,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
        error_category=classify(exc).category.value,
    )


def _accumulate_repairs(total: dict[str, int], report: HygieneReport) -> None:
    """Fold one turn's hygiene report into the run-wide repair tally (for trace)."""
    for kind, count in report.repairs.items():
        total[kind.value] = total.get(kind.value, 0) + count


def _assemble_prompt(
    base_system: str,
    skills_catalog: str,
    memory_ctx: str,
    user_msg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Order messages stable→variable so the auto prefix cache can hit (D2).

    The cacheable prefix is the first system message: the base system prompt plus
    the <available_skills> catalog (already including its scan instruction), which
    is stable across requests — it changes only when the deployment's skill set
    does. Per-request variable content (memory injection) is carried in a separate
    second system message after it, so changing memory never rewrites the base
    prefix. Either variable section is omitted when empty so the prefix stays
    maximal.
    """
    base = f"{base_system}\n\n{skills_catalog}" if skills_catalog else base_system
    messages: list[dict[str, Any]] = [{"role": "system", "content": base}]
    if memory_ctx:
        messages.append({"role": "system", "content": memory_ctx})
    messages.append(user_msg)
    return messages


def _extract_cache_tokens(usage: Any) -> dict[str, int] | None:
    """Best-effort pull of prompt-cache metrics off a usage object (D3).

    Reads Anthropic-style top-level fields (`cache_read_input_tokens`,
    `cache_creation_input_tokens`) and the OpenAI-style nested
    `prompt_tokens_details.cached_tokens`. Backends that report none of these
    yield None so the trace simply omits the field — never an error.
    """
    if usage is None:
        return None
    found: dict[str, int] = {}
    for field in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(usage, field, None)
        if isinstance(value, int):
            found[field] = value
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details is not None else None
    if isinstance(cached, int):
        found["cached_tokens"] = cached
    return found or None


ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]


async def run(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    is_sub_agent: bool = False,
    reply_func: ReplyFunc | None = None,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
    max_turns: int | None = None,
    max_consecutive_failures: int | None = None,
    force_model: str | None = None,
    disabled_skills_trace: list[dict[str, str]] | None = None,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
) -> str:
    """Async agent loop accepting a messages list. Return the final text reply.

    When is_sub_agent=True the sub_agent tool is excluded from the tool schema
    so child agents cannot spawn further sub-agents.
    When allowed_tools is set, only matching tools (fnmatch patterns) are exposed.
    Skills are surfaced to the model as an <available_skills> catalog inside the
    prebuilt system prompt; run() does no skill injection itself — the catalog is
    assembled by the message-building entry points (run_sync / run_stream /
    im_gateway) and the model loads full content on demand via the read_skill tool.
    max_turns / max_consecutive_failures override the deployment defaults.
    force_model forces this run's LLM calls onto a specific model via a
    request-level routing override (MR1); None keeps task_type routing unchanged.
    """
    # Image-bearing messages route to the vision model (D6); raises here if
    # images are present but no vision route is configured, before any LLM call.
    # force_model layers a request-level override onto that route (MR1); when
    # None the call stays byte-identical to task_type routing.
    route = _select_route(messages)
    if force_model is None:
        client, cfg = get_async_client_and_config(route)
    else:
        client, cfg = get_async_client_and_config(route, override=RouteOverride(model=force_model))

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
    # Override forces a single model with no fallback (D3); cfg.fallbacks is
    # already empty here, but be explicit so the intent survives refactors.
    models_to_try = [cfg.model] if force_model is not None else [cfg.model, *cfg.fallbacks]
    model_used = cfg.model

    controller, loop_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=True,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}

    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break

        # In-place content assignment (messages[:] = ...) keeps the caller's list
        # reference live: callers (e.g. im_gateway.normalizer) rely on run() mutating
        # the passed `messages` so session_mgr.save() persists the full conversation.
        # Rebinding (messages = ...) would detach it and lose appended turns.
        messages[:] = maybe_compress(messages)
        # D4b: inject the loop warning AFTER compression so a same-round compaction
        # cannot swallow it; it must be present in the sequence sent to the LLM.
        _maybe_inject_loop_warning(messages, state)
        try:
            clean, report = sanitize(messages)
        except MessageContractError as exc:
            # Unrepairable sequence: fail locally before the LLM call (design D3).
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            return ""
        messages[:] = clean
        _accumulate_repairs(hygiene_repairs, report)
        try:
            response, model_used = await _call_with_fallback(
                client, cfg, messages, schemas, models_to_try
            )
        except Exception as exc:
            # Record the error class on the trace before propagating (design D4).
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            raise
        state.turn += 1
        models_to_try = [model_used]  # stick with the winning model for subsequent turns
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump())  # dict for JSON serializability (session persistence)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            failed = False
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
                result = "\n".join(
                    f"[{r.name}] {'ERROR: ' + r.error if r.error else r.result}"
                    for r in sub_results
                )
                state.consecutive_failures = 0
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
                        # Rejection terminates at the next checkpoint; the placeholder
                        # tool_result keeps the message sequence valid for the LLM.
                        state.approval_rejected = True
                        result = (
                            f"tool execution {decision}: user did not approve {tc.function.name}"
                        )
                    else:
                        result, failed = await _safe_dispatch(
                            tc.function.name, tc.function.arguments, is_sub_agent
                        )
                        state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
                else:
                    result, failed = await _safe_dispatch(
                        tc.function.name, tc.function.arguments, is_sub_agent
                    )
                    state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            state.record_tool_call(
                tc.function.name,
                arg_fingerprint(tc.function.arguments, loop_checker.ignore_arg_keys),
                result_digest(result),
                not failed,
                window=loop_checker.window,
            )

    reply = (msg.content if msg is not None else None) or ""
    usage = response.usage if response else None
    user_input = _first_user_input(messages)
    log_run(
        user_input,
        reply,
        messages,
        time.monotonic() - start,
        usage,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
        stop_reason=stop_reason,
        hygiene_repairs=hygiene_repairs or None,
        cache_tokens=_extract_cache_tokens(usage),
        disabled_skills_trace=disabled_skills_trace,
    )
    extract_and_save(user_input, messages, user_id=user_id)
    return reply


def run_sync(
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
) -> str:
    """Synchronous wrapper around run() for CLI use.

    Skills are offered as an <available_skills> catalog in the system prompt; the
    model loads any it needs via the read_skill tool. The CLI scans skills on each
    call so freshly added skills are picked up.
    """
    scan_skills()
    memory_ctx = load_memories(user_id=user_id)
    skills_catalog = available_skills_prompt()
    disabled_trace = collect_disabled_trace() or None

    messages = _assemble_prompt(
        system_prompt, skills_catalog, memory_ctx, {"role": "user", "content": user_input}
    )

    return asyncio.run(
        run(
            messages,
            user_id=user_id,
            system_prompt=system_prompt,
            disabled_skills_trace=disabled_trace,
        )
    )


async def run_stream(
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
    max_turns: int | None = None,
    max_consecutive_failures: int | None = None,
    images: list[tuple[bytes, str]] | None = None,
    force_model: str | None = None,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, done.
    text_delta events stream as tokens arrive from the LLM.

    When `images` (a list of (bytes, mime)) is given, the user message is built
    as a content-block array (text + image_url blocks, base64-inlined) and the
    run routes to the vision model (AR21). Plain-text input is unchanged.

    Termination covers max_turns / consecutive_failures; approval gating is not
    performed on the streaming path, so approval_rejected does not apply here.
    """
    memory_ctx = load_memories(user_id=user_id)
    skills_catalog = available_skills_prompt()
    disabled_trace = collect_disabled_trace() or None

    if images:
        user_msg = build_message_with_images(user_input, images)
    else:
        user_msg = {"role": "user", "content": user_input}
    messages: list[Any] = _assemble_prompt(system_prompt, skills_catalog, memory_ctx, user_msg)

    # Route to vision when images are present; raises before any LLM call if
    # images are present but no vision route is configured (D6, option A).
    # force_model layers a request-level override (MR1); None keeps task_type
    # routing byte-identical.
    route = _select_route(messages)
    if force_model is None:
        client, cfg = get_async_client_and_config(route)
    else:
        client, cfg = get_async_client_and_config(route, override=RouteOverride(model=force_model))

    start = time.monotonic()
    reply = ""
    models_to_try = [cfg.model] if force_model is not None else [cfg.model, *cfg.fallbacks]
    model_used = cfg.model
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cache_tokens: dict[str, int] | None = None

    controller, loop_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=False,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}

    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break
        state.turn += 1
        messages = maybe_compress(messages)
        # D4b: inject the loop warning after compression, before sanitize/LLM call.
        _maybe_inject_loop_warning(messages, state)
        try:
            messages, report = sanitize(messages)
        except MessageContractError as exc:
            yield {"type": "error", "content": str(exc)}
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            return
        _accumulate_repairs(hygiene_repairs, report)

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
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            return

        stream = cast(AsyncStream[ChatCompletionChunk], stream)
        async for chunk in stream:
            if chunk.usage:
                total_prompt_tokens += chunk.usage.prompt_tokens
                total_completion_tokens += chunk.usage.completion_tokens
                chunk_cache = _extract_cache_tokens(chunk.usage)
                if chunk_cache is not None:
                    cache_tokens = chunk_cache
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
            result, failed = await _safe_dispatch(name, args, False)
            state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
            yield {"type": "tool_result", "name": name, "content": result}
            messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": result})
            state.record_tool_call(
                name,
                arg_fingerprint(args, loop_checker.ignore_arg_keys),
                result_digest(result),
                not failed,
                window=loop_checker.window,
            )

    yield {"type": "done", "content": reply}

    from openai.types import CompletionUsage as _CU

    stream_usage: _CU | None = (
        _CU(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )
        if total_prompt_tokens or total_completion_tokens
        else None
    )
    log_run(
        user_input,
        reply,
        messages,
        time.monotonic() - start,
        usage=stream_usage,
        model_used=model_used,
        user_id=user_id,
        agent_name=agent_name,
        stop_reason=stop_reason,
        hygiene_repairs=hygiene_repairs or None,
        cache_tokens=cache_tokens,
        disabled_skills_trace=disabled_trace,
    )
    extract_and_save(user_input, messages, user_id=user_id)
