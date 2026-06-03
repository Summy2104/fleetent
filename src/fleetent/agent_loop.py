"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import asyncio
import inspect
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, cast

import structlog
from openai import APIStatusError, AsyncOpenAI, AsyncStream, RateLimitError
from openai.types.chat import ChatCompletionChunk

import fleetent.tools  # noqa: F401  # side-effect: register built-in tools
from fleetent.budget import BudgetChecker, BudgetConfig, BudgetUsage, grace_max_tokens
from fleetent.cancellation import CancellationChecker, CancelToken
from fleetent.context_mgr import (
    AntiFlapState,
    apply_anti_flap,
    load_anti_flap_state,
    maybe_compress,
    save_anti_flap_state,
)
from fleetent.error_classifier import classify
from fleetent.eval_logger import log_run
from fleetent.governance.agent_policy import check_tool_access
from fleetent.governance.permission_gate import _default_gate
from fleetent.integrations.sandbox import Mode, is_code_execution_enabled
from fleetent.intelligence.long_term_ctx import ContextSource, build_context
from fleetent.intelligence.memory import extract_and_update
from fleetent.loop_detector import LoopDetectionChecker, arg_fingerprint, result_digest
from fleetent.message_hygiene import HygieneReport, MessageContractError, sanitize
from fleetent.model import router as model_router
from fleetent.model.provider_health import ProviderHealthCache, get_health_cache
from fleetent.model.router import RouteConfig, RouteOverride, get_async_client_and_config
from fleetent.observability import (
    InjectedContextTrace,
    TraceEvent,
    record_injected_context,
    record_trace_event,
)
from fleetent.skills import available_skills_prompt, collect_disabled_trace
from fleetent.skills import match as match_skill  # noqa: F401  # patch target + API parity
from fleetent.skills import scan as scan_skills
from fleetent.sub_agent import SubAgentExecutor
from fleetent.termination import (
    ApprovalRejectedChecker,
    ConsecutiveFailuresChecker,
    GuardrailChecker,
    LoopState,
    StopReason,
    TerminationController,
    resolve_limits,
)
from fleetent.tool_guardrails import GuardrailAction, evaluate_guardrail
from fleetent.tools.multimodal import build_message_with_images, has_image_block
from fleetent.tools.registry import (
    ToolContext,
    dispatch,
    get_effective_timeout,
    get_risk_level,
    get_schemas,
    is_self_truncating,
)
from fleetent.tools.result_truncation import truncate_tool_result

logger = structlog.get_logger(__name__)

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"

ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]

# The single code-execution tool gated by the SB3 three-state mode. Filtered out
# of an agent's schema (the one enablement point, D1) when code execution is not
# enabled for that (mode, features) pair.
_RUN_CODE_TOOL = "run_code"


def _filter_code_execution(
    schemas: list[Any],
    sandbox_mode: Mode | None,
    agent_features: dict[str, Any] | None,
) -> list[Any]:
    """Drop `run_code` from schemas when code execution is disabled (SB3 D1).

    The single enablement point: both the global `off` gate and the agent-level
    `code_execution=false` gate collapse into this filter, sitting alongside the
    existing `allowed_tools` schema filter. `sandbox_mode is None` means the caller
    opted out of SB3 gating entirely — schemas pass through byte-identical, keeping
    existing callers' behaviour unchanged.
    """
    if sandbox_mode is None:
        return schemas
    code_execution = (agent_features or {}).get("code_execution")
    if is_code_execution_enabled(sandbox_mode, code_execution):
        return schemas
    return [s for s in schemas if s["function"]["name"] != _RUN_CODE_TOOL]


# Corrective warning injected when the loop-detection checker first flags a
# suspected loop (AR4 D3/D4). Plain `user` role (D4) so it is not merged with the
# leading system prompt by message_hygiene and stays visible on the next turn.
_LOOP_WARNING_TEXT = (
    "检测到你正在重复调用同一工具且似乎没有进展，请改用其它方式或直接给出当前结论。"
)

# Placeholder tool_result content when the AR10 guardrail short-circuits a call:
# it both keeps the message sequence valid (every tool_call needs a tool_result)
# and feeds the correction back to the model so it changes approach.
_GUARDRAIL_FEEDBACK_TEXT = (
    "已跳过本次工具调用：检测到相同工具、相同参数连续重复多次。请改用其它方式或直接给出当前结论。"
)

# Appended as a final `user` message when a budget dimension is exhausted (AR2 D3):
# the Grace Call asks the model to summarize progress in one go without further
# tool use, so the user gets a graceful conclusion instead of a half-cut reply.
_GRACE_CALL_TEXT = "已达到本次任务的预算上限。请用一段话总结当前进展与已得结论，不要再调用工具。"


def _resolve_budget_config(
    max_turns: int | None,
    max_tokens: int | None,
) -> BudgetConfig:
    """Resolve the two-dimensional budget: call param > Settings > default (D1).

    The step dimension reuses the existing max_turns resolution (resolve_limits);
    the token dimension comes from Settings (NO_LIMIT by default) unless overridden.
    """
    mt, _ = resolve_limits(max_turns, None)
    if max_tokens is not None:
        return BudgetConfig(max_turns=mt, max_tokens=max_tokens)
    from fleetent.config import Settings

    s = Settings()
    return BudgetConfig(max_turns=mt, max_tokens=s.agent_max_tokens)


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


def _resolve_guardrail_threshold(guardrail_repeat_threshold: int | None) -> int:
    """Resolve the AR10 guardrail threshold: call param > Settings > default (D1)."""
    if guardrail_repeat_threshold is not None:
        return guardrail_repeat_threshold
    from fleetent.config import Settings

    return Settings().guardrail_repeat_threshold


def _resolve_parallel_max() -> int:
    """Resolve the AR3 single-round tool concurrency cap from Settings (D7)."""
    from fleetent.config import Settings

    return Settings().agent_tool_parallel_max


def _resolve_default_tool_timeout() -> float:
    """Global default per-tool timeout from Settings (T2), resolved once per run."""
    from fleetent.config import Settings

    return Settings().tool_default_timeout_seconds


def _agent_bound_to_server(server_id: str, allowed_tools: list[str] | None) -> bool:
    """Whether this agent can use any of a server's `{id}__*` tools (MCP4 D3).

    allowed_tools=None means every tool is permitted → bound to every server.
    Otherwise bound iff some registered tool in the namespace passes the whitelist.
    A startup-failed server has no registered tools, so it only binds an all-tools
    agent (allowed_tools=None) — a documented limitation."""
    if allowed_tools is None:
        return True
    from fleetent.tools.registry import _registry

    prefix = f"{server_id}__"
    return any(
        name.startswith(prefix) and check_tool_access(name, allowed_tools) for name in _registry
    )


def _strict_blocked_servers(allowed_tools: list[str] | None) -> list[str]:
    """Handle MCP degradation for this agent (MCP4): return strict-mode unavailable
    servers the agent is bound to (→ stop); log degrade(warning)/silent(debug) for
    bound non-strict unavailable servers. No MCP servers → empty, zero overhead."""
    from fleetent.integrations.mcp import client as mcp_client

    strict_blocked: list[str] = []
    for server_id, mode in mcp_client.unavailable_servers():
        if not _agent_bound_to_server(server_id, allowed_tools):
            continue
        if mode == "strict":
            strict_blocked.append(server_id)
        elif mode == "silent":
            logger.debug("mcp_degraded_silent", server_id=server_id)
        else:
            logger.warning("mcp_degraded", server_id=server_id)
    return strict_blocked


def _strict_unavailable_reply(blocked: list[str]) -> str:
    return (
        "无法运行：所依赖的 MCP 服务（"
        + ", ".join(blocked)
        + "）当前不可用，且其降级模式为 strict（严格）。已终止本次运行。"
    )


def _load_flap_state(session_id: str | None) -> AntiFlapState | None:
    """Load per-session anti-flap state (AR17); None disables gating (CLI / no session).

    Defensive: a persistence failure degrades to ungated AR12 compression rather
    than breaking the run.
    """
    if not session_id:
        return None
    try:
        return load_anti_flap_state(session_id)
    except Exception as exc:  # observability/governance must not break the run
        logger.warning("anti_flap_load_failed", session_id=session_id, error=str(exc))
        return None


def _save_flap_state(session_id: str | None, state: AntiFlapState | None) -> None:
    if not session_id or state is None:
        return
    try:
        save_anti_flap_state(session_id, state)
    except Exception as exc:
        logger.warning("anti_flap_save_failed", session_id=session_id, error=str(exc))


def _gated_compress(
    messages: list[Any],
    flap_state: AntiFlapState | None,
    *,
    session_id: str | None,
    user_id: str | None,
    agent_name: str | None,
) -> tuple[list[Any], AntiFlapState | None]:
    """Auto-compress one turn: anti-flap gated when a session state exists, else AR12."""
    if flap_state is not None:
        return apply_anti_flap(
            messages, flap_state, session_id=session_id, user_id=user_id, agent_name=agent_name
        )
    return (
        maybe_compress(messages, session_id=session_id, user_id=user_id, agent_name=agent_name),
        None,
    )


def _setup_layered_budget(
    session_id: str | None, user_id: str | None, agent_name: str | None
) -> tuple[Any, Any, dict[Any, str | None]]:
    """Build the AR18 layered-budget checker/store, or (None, None, {}) when no cap
    is configured (dormant by default → zero behaviour/DB change for plain runs)."""
    from fleetent import layered_budget as lbud

    config = lbud.LayeredBudgetConfig.from_settings()
    if not config.has_any_cap():
        return None, None, {}
    store = lbud.BudgetStore()
    keys: dict[Any, str | None] = {
        lbud.BudgetScope.session: session_id,
        lbud.BudgetScope.user: user_id,
        lbud.BudgetScope.agent: agent_name,
        lbud.BudgetScope.global_: lbud.GLOBAL_KEY,
    }
    checker = lbud.LayeredBudgetChecker(config, store, keys, clock=lbud.utc_now)
    return checker, store, keys


def _layered_budget_add(
    store: Any, keys: dict[Any, str | None], prompt: int, completion: int
) -> None:
    """Fold one main-loop turn into each cross-run scope with a present key (AR18)."""
    if store is None:
        return
    from fleetent import layered_budget as lbud

    now = lbud.utc_now()
    for scope in lbud.CROSS_RUN_SCOPES:
        key = keys.get(scope)
        if key is None:
            continue
        store.add(scope, key, prompt or 0, completion or 0, now=now)


def _build_controller(
    max_turns: int | None,
    max_consecutive_failures: int | None,
    *,
    include_approval: bool,
    budget_config: BudgetConfig,
    budget_usage: BudgetUsage,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
    cancel_token: CancelToken | None = None,
) -> tuple[TerminationController, LoopDetectionChecker, BudgetChecker]:
    """Assemble the termination controller with the active checkers.

    The budget checker (AR2) replaces the retired MaxTurnsChecker: the step
    dimension is now one of two budget dimensions (turns / tokens), and
    any exhausted dimension produces `budget_exceeded` (not `max_turns`). The
    `StopReason.max_turns` enum member is retained but the loop no longer produces
    it (design D2). The budget checker reads the same per-run `budget_usage` the
    loop accumulates into each turn, and is returned so the loop can read the
    triggering dimension for the trace.

    The loop-detection checker (AR4) registers AFTER it so the established
    termination priority (budget / consecutive_failures / approval_rejected) is
    unchanged relative to the old (max_turns / ...) ordering.

    The cancellation checker (AR19) registers first so an already-cancelled token
    short-circuits before any other reason; with a never-cancelling default token
    it can never fire, keeping the no-token path byte-identical.
    """
    _, mcf = resolve_limits(max_turns, max_consecutive_failures)
    threshold, ignore_keys = _resolve_loop_config(loop_repeat_threshold, loop_ignore_arg_keys)
    controller = TerminationController()
    if cancel_token is not None:
        controller.register(CancellationChecker(cancel_token))
    budget_checker = BudgetChecker(budget_config, budget_usage)
    controller.register(budget_checker)
    controller.register(ConsecutiveFailuresChecker(mcf))
    if include_approval:
        controller.register(ApprovalRejectedChecker())
    controller.register(GuardrailChecker())
    loop_checker = LoopDetectionChecker(threshold, ignore_keys)
    controller.register(loop_checker)
    return controller, loop_checker, budget_checker


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
    name: str,
    arguments: str | dict[str, Any],
    is_sub_agent: bool,
    cancel_token: CancelToken | None = None,
    tool_context: ToolContext | None = None,
    user_id: str | None = None,
    default_timeout: float | None = None,
) -> tuple[str, bool]:
    """Dispatch a tool, normalizing a crash into (error_text, failed=True).

    Returning instead of raising keeps a tool crash from killing the loop and
    lets the consecutive-failures checker observe it. The cancel token and the
    execution context are passed out-of-band; dispatch injects each only into
    tools that opt in (AR19 D3 / SB3 D5). `user_id` is threaded so connector
    tools can resolve per-user credentials at dispatch time.
    """
    # T2: race the tool against its effective timeout. The per-tool token carries
    # its own deadline AND links the run-level token via `parent`, so the tool
    # observes both its timeout and a session-wide cancel. asyncio.wait_for is the
    # hard "stop waiting" guarantee even for tools that never poll the token.
    timeout = get_effective_timeout(name, default_timeout)
    child = CancelToken(deadline=time.monotonic() + timeout, parent=cancel_token)
    try:
        result = dispatch(
            name,
            arguments,
            is_sub_agent=is_sub_agent,
            cancel_token=child,
            tool_context=tool_context,
            user_id=user_id,
        )
        if inspect.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout=timeout)
        return result, False
    except TimeoutError:  # asyncio.wait_for timeout → tool_timeout (AR5 reserved code)
        child.cancel()
        return f"tool execution timed out after {timeout}s", True
    except Exception as exc:  # normalized for the loop; not swallowed silently
        return f"tool execution error: {exc}", True


# ── AR3: parallel tool dispatch (three-phase: plan → execute → backfill) ────────


@dataclass
class _PlanSlot:
    """One LLM tool_call's plan outcome, keyed to its original `tool_calls` index.

    The planning phase (serial) produces one slot per `tool_call`. A slot is either
    a *placeholder* (guardrail short-circuit/stop, approval rejected, or a sub_agent
    result already computed) carrying its final `(content, failed)`, or *pending*
    execution carrying the `(name, args)` to dispatch in the parallel phase. The
    backfill phase (serial, original order) reads each slot and appends the tool
    message, records the call, and folds `consecutive_failures` — preserving the
    sequential per-result semantics (D4) regardless of completion order.
    """

    tc_id: str
    name: str
    tc_fp: str
    # Raw arguments (str or dict) for a pending dispatch; unused for placeholders.
    args: str | dict[str, Any] = ""
    # When set, this slot is already resolved (no dispatch). (content, failed).
    placeholder: tuple[str, bool] | None = None
    # A custom awaitable factory for non-dispatch pending slots (D6: sub_agent runs
    # its own SubAgentExecutor inside the batch instead of going through dispatch).
    runner: Callable[[], Coroutine[Any, Any, tuple[str, bool]]] | None = None
    # Whether this slot updates consecutive_failures at backfill (D4). Guardrail
    # and approval-rejected slots leave the counter untouched (status-quo parity).
    counts_failure: bool = True
    # Resource key for D5 sandbox serialization; same key → serialized, None → free.
    resource_key: str | None = None


def _resource_key(name: str, session_id: str | None) -> str | None:
    """D5: the shared-container key for stateful tools, or None for free tools.

    `run_code` reuses the session sandbox container (SB2), so multiple `run_code`
    calls in one round must serialize on that container to avoid concurrent
    `docker exec` interfering with shared filesystem/process state. Tools without a
    shared container return None and run unconstrained in the parallel batch.
    """
    if name == _RUN_CODE_TOOL:
        return f"{_RUN_CODE_TOOL}:{session_id or ''}"
    return None


async def _run_serial_group(
    slots: list[_PlanSlot],
    *,
    is_sub_agent: bool,
    token: CancelToken,
    tool_context: ToolContext,
    user_id: str,
    default_tool_timeout: float | None = None,
) -> list[tuple[str, bool]]:
    """Dispatch a same-resource-key group strictly in order (D5).

    Same-container stateful tools collapse into one sequential coroutine so the
    batch's gather still sees a single awaitable per group; results stay aligned
    to the group's slot order. T2's configurable default timeout flows to each
    `_safe_dispatch`.
    """
    out: list[tuple[str, bool]] = []
    for slot in slots:
        if slot.runner is not None:
            out.append(await slot.runner())
        else:
            out.append(
                await _safe_dispatch(
                    slot.name,
                    slot.args,
                    is_sub_agent,
                    token,
                    tool_context,
                    user_id=user_id,
                    default_timeout=default_tool_timeout,
                )
            )
    return out


async def _execute_pending(
    pending: list[_PlanSlot],
    *,
    is_sub_agent: bool,
    token: CancelToken,
    tool_context: ToolContext,
    user_id: str,
    parallel_max: int,
    default_tool_timeout: float | None = None,
) -> dict[str, tuple[str, bool]]:
    """Phase two (D1/D5/D7): run pending slots concurrently, return id→(text,failed).

    Slots sharing a D5 resource key are collapsed into one serial coroutine (group),
    so a group occupies a single gather slot; free slots each occupy their own.
    Coroutines are split into batches of at most `parallel_max` (D7) run serially;
    `<=1` degrades to one-at-a-time (status-quo sequential). `asyncio.gather`
    returns in input order, but results are mapped back by `tc_id` so the backfill
    phase can index by original `tool_calls` order regardless. `return_exceptions`
    is NOT set: `_safe_dispatch` already normalizes tool faults, so any escaping
    exception is a real bug and must propagate (CLAUDE.md: do not swallow).
    """
    # Group same-key slots (preserving order); free slots stay singletons.
    groups: list[list[_PlanSlot]] = []
    key_to_group: dict[str, list[_PlanSlot]] = {}
    for slot in pending:
        if slot.resource_key is None:
            groups.append([slot])
            continue
        group = key_to_group.get(slot.resource_key)
        if group is None:
            group = []
            key_to_group[slot.resource_key] = group
            groups.append(group)
        group.append(slot)

    results: dict[str, tuple[str, bool]] = {}
    batch_size = parallel_max if parallel_max > 1 else 1
    for start in range(0, len(groups), batch_size):
        batch = groups[start : start + batch_size]
        gathered = await asyncio.gather(
            *(
                _run_serial_group(
                    group,
                    is_sub_agent=is_sub_agent,
                    token=token,
                    tool_context=tool_context,
                    user_id=user_id,
                    default_tool_timeout=default_tool_timeout,
                )
                for group in batch
            )
        )
        for group, group_results in zip(batch, gathered, strict=True):
            for slot, res in zip(group, group_results, strict=True):
                results[slot.tc_id] = res
    return results


async def _plan_run_slots(
    tool_calls: list[Any],
    *,
    state: LoopState,
    loop_checker: LoopDetectionChecker,
    guardrail_threshold: int,
    is_sub_agent: bool,
    reply_func: ReplyFunc | None,
    user_id: str,
    session_id: str | None,
) -> list[_PlanSlot]:
    """Phase one for run() (D2/D3/D6): serial, original order — produce one slot
    per tool_call. Guardrail and (medium/high) approval are decided here in order;
    sub_agent becomes a pending slot whose runner self-gathers (D6). The result
    list preserves original `tool_calls` order so backfill can index 0..N-1.
    """
    slots: list[_PlanSlot] = []
    for tc in tool_calls:
        if not hasattr(tc, "function"):
            continue
        name = tc.function.name
        tc_fp = arg_fingerprint(tc.function.arguments, loop_checker.ignore_arg_keys)
        # AR10 guardrail (serial — depends on per-call streak in `state`, D2).
        action = evaluate_guardrail(state, name, tc_fp, guardrail_threshold)
        if action is not GuardrailAction.proceed:
            if action is GuardrailAction.short_circuit:
                state.loop_warning_injected = True
            else:
                state.guardrail_tripped = True
            slots.append(
                _PlanSlot(
                    tc_id=tc.id,
                    name=name,
                    tc_fp=tc_fp,
                    placeholder=(_GUARDRAIL_FEEDBACK_TEXT, False),
                    counts_failure=False,
                )
            )
            continue
        if name == _SUB_AGENT_TOOL and not is_sub_agent:
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

            async def _sub_agent_runner(tasks: Any = tasks) -> tuple[str, bool]:
                sub_results = await SubAgentExecutor().run(
                    tasks=tasks,
                    parent_user_id=user_id,
                    parent_agent_id=None,
                    parent_session_id="",
                )
                text = "\n".join(
                    f"[{r.name}] {'ERROR: ' + r.error if r.error else r.result}"
                    for r in sub_results
                )
                return text, False

            slots.append(_PlanSlot(tc_id=tc.id, name=name, tc_fp=tc_fp, runner=_sub_agent_runner))
            continue
        risk = get_risk_level(name)
        if risk in ("medium", "high") and reply_func is not None:
            tool_args = (
                json.loads(tc.function.arguments)
                if isinstance(tc.function.arguments, str)
                else tc.function.arguments
            )
            approval_id = str(uuid.uuid4())[:8]
            # D3: approvals are requested serially in original order; only approved
            # tools enter the parallel batch — never concurrent approval prompts.
            decision = await _default_gate.request_approval(
                approval_id=approval_id,
                risk_level=risk,
                tool_name=name,
                tool_args=tool_args,
                requester_user_id=user_id,
                reply_func=reply_func,
            )
            if decision != "approved":
                state.approval_rejected = True
                slots.append(
                    _PlanSlot(
                        tc_id=tc.id,
                        name=name,
                        tc_fp=tc_fp,
                        placeholder=(
                            f"tool execution {decision}: user did not approve {name}",
                            False,
                        ),
                        counts_failure=False,
                    )
                )
                continue
        slots.append(
            _PlanSlot(
                tc_id=tc.id,
                name=name,
                tc_fp=tc_fp,
                args=tc.function.arguments,
                resource_key=_resource_key(name, session_id),
            )
        )
    return slots


def _backfill_slots(
    slots: list[_PlanSlot],
    results: dict[str, tuple[str, bool]],
    *,
    messages: list[Any],
    state: LoopState,
    loop_checker: LoopDetectionChecker,
) -> None:
    """Phase three (D1/D4): serial, original `tool_calls` order. Append each tool
    message, record the call into the loop-detection window, and fold
    `consecutive_failures` per-result — identical to sequential per-tool updates.
    """
    for slot in slots:
        content, failed = slot.placeholder if slot.placeholder is not None else results[slot.tc_id]
        if slot.counts_failure:
            state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
        # T4: cap the messages copy (self-truncating tools manage their own size).
        tool_content = content if is_self_truncating(slot.name) else truncate_tool_result(content)
        messages.append({"role": "tool", "tool_call_id": slot.tc_id, "content": tool_content})
        state.record_tool_call(
            slot.name,
            slot.tc_fp,
            result_digest(content),
            not failed,
            window=loop_checker.window,
        )


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


def _budget_add(usage: BudgetUsage, response_usage: Any) -> None:
    """Fold one main-loop turn into the budget accumulator (D1).

    Reads prompt/completion tokens off the response usage; a missing or non-int
    usage still counts the turn (step dimension) with zero tokens, so the turns
    dimension never silently stops accumulating.
    """
    prompt = getattr(response_usage, "prompt_tokens", 0)
    completion = getattr(response_usage, "completion_tokens", 0)
    usage.add(
        prompt if isinstance(prompt, int) else 0,
        completion if isinstance(completion, int) else 0,
    )


async def _grace_call(
    client: AsyncOpenAI,
    cfg: RouteConfig,
    messages: list[Any],
    schemas: list[Any],
    models: list[str],
    budget_max_tokens: int,
    partial_reply: str,
) -> str:
    """Final non-streaming summarizing call on budget exhaustion (AR2 D3).

    Appends the grace instruction and asks for a one-paragraph summary under a
    token cap reserved from the budget's token dimension. On any failure
    (timeout/error/empty) the call degrades to the partial reply already
    accumulated — logged, never retried, never crashing.
    """
    grace_messages = [*messages, {"role": "user", "content": _GRACE_CALL_TEXT}]
    reserved = grace_max_tokens(budget_max_tokens)
    try:
        resp = await client.chat.completions.create(
            model=models[0],
            messages=grace_messages,
            tools=schemas,
            max_tokens=reserved,
            **cfg.params,
        )
        summary = resp.choices[0].message.content or ""
        if not summary:
            logger.warning("grace_call_empty_fallback_partial")
            return partial_reply
        return summary
    except Exception as exc:  # degrade to partial result; not swallowed silently
        logger.warning("grace_call_failed_fallback_partial", error=str(exc))
        return partial_reply


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
    user_msg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Order messages stable→variable so the auto prefix cache can hit (D2).

    The cacheable prefix is the first system message: the base system prompt plus
    the <available_skills> catalog (already including its scan instruction), stable
    across requests. Per-request long-term context (memory + knowledge) is appended
    by run()/run_stream() via build_context after this, so the base prefix stays
    stable (memory unified onto intelligence/long_term_ctx; class C).
    """
    base = f"{base_system}\n\n{skills_catalog}" if skills_catalog else base_system
    messages: list[dict[str, Any]] = [{"role": "system", "content": base}]
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


# Long-term context (knowledge base + memory) injection + observability trace
# wiring, grafted from main's agent_loop during the architecture merge (follow-up
# class A). build_context / trace recording are best-effort at the call sites in
# run()/run_stream() so a missing DB or disabled KB never breaks a run.
_LONG_TERM_CONTEXT_HEADER = "[Long-term context]"


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
    max_tokens: int | None = None,
    force_model: str | None = None,
    disabled_skills_trace: list[dict[str, str]] | None = None,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
    guardrail_repeat_threshold: int | None = None,
    cancel_token: CancelToken | None = None,
    sandbox_mode: Mode | None = None,
    agent_features: dict[str, Any] | None = None,
    session_id: str | None = None,
    allowed_skills: list[str] | None = None,
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
    allowed_skills is a per-agent skill-catalog narrowing (agent-skill-scoping);
    run() receives a pre-assembled messages list (the <available_skills> catalog is
    built by the message-building entry points), so it does not re-render the
    catalog itself — the param is accepted for API symmetry with run_stream and for
    a future run()-builds-catalog path, and does not re-filter here (avoiding double
    narrowing). Callers narrow at the point they build the catalog.
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

    # SB3 D1: the single code-execution enablement point — drop run_code from this
    # agent's schema when the (mode, features) pair disables it (alongside the
    # allowed_tools filter above).
    schemas = _filter_code_execution(schemas, sandbox_mode, agent_features)

    # SB3 D5: execution-time context channel for run_code (session/agent/features),
    # injected out-of-band only into tools that opt in; harmless for the rest.
    tool_context = ToolContext(
        agent_name=agent_name, features=agent_features or {}, session_id=session_id
    )

    start = time.monotonic()
    run_id = str(uuid.uuid4())
    user_input = _first_user_content(messages)
    # Class-A wiring: inject long-term context (KB + memory) and record the
    # injected-context trace. Best-effort — a missing DB / disabled KB must not
    # break the run (mirrors the sandbox/eval_logger best-effort pattern).
    try:
        built_context = await build_context(user_id, user_input, agent_name or "", cfg.max_tokens)
        _append_system_context(messages, system_prompt, built_context.text)
        _record_injected_context(run_id, built_context.sources)
    except Exception as exc:  # noqa: BLE001 — long-term context is auxiliary
        logger.debug("long_term_context_skipped", error=str(exc))
    # MCP4: a strict-mode MCP server the agent is bound to is unavailable → stop up
    # front with a clear error (rather than run without its tools). Also logs
    # degrade/silent degradations for bound servers. No MCP servers → no-op.
    strict_blocked = _strict_blocked_servers(allowed_tools)
    if strict_blocked:
        reply = _strict_unavailable_reply(strict_blocked)
        log_run(
            _first_user_input(messages),
            reply,
            messages,
            time.monotonic() - start,
            None,
            user_id=user_id,
            agent_name=agent_name,
            stop_reason=StopReason.mcp_strict_unavailable,
        )
        return reply
    response = None
    msg: Any = None
    # Override forces a single model with no fallback (D3); cfg.fallbacks is
    # already empty here, but be explicit so the intent survives refactors.
    models_to_try = [cfg.model] if force_model is not None else [cfg.model, *cfg.fallbacks]
    model_used = cfg.model

    # None → a never-cancelling default token, keeping the no-token path identical.
    token = cancel_token if cancel_token is not None else CancelToken()
    budget_config = _resolve_budget_config(max_turns, max_tokens)
    budget_usage = BudgetUsage()
    controller, loop_checker, budget_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=True,
        budget_config=budget_config,
        budget_usage=budget_usage,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
        cancel_token=token,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}
    guardrail_threshold = _resolve_guardrail_threshold(guardrail_repeat_threshold)
    parallel_max = _resolve_parallel_max()
    default_tool_timeout = _resolve_default_tool_timeout()
    flap_state = _load_flap_state(session_id)
    layered_checker, layered_store, layered_keys = _setup_layered_budget(
        session_id, user_id, agent_name
    )
    if layered_checker is not None:
        controller.register(layered_checker)

    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break

        # In-place content assignment (messages[:] = ...) keeps the caller's list
        # reference live: callers (e.g. im_gateway.normalizer) rely on run() mutating
        # the passed `messages` so session_mgr.save() persists the full conversation.
        # Rebinding (messages = ...) would detach it and lose appended turns.
        _compressed, flap_state = _gated_compress(
            messages, flap_state, session_id=session_id, user_id=user_id, agent_name=agent_name
        )
        messages[:] = _compressed
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
        # D1: accumulate this turn's usage immediately (step + tokens + cost) so the
        # BudgetChecker judges on up-to-date usage at the next checkpoint — not on a
        # single end-of-loop response.usage. Compression's internal LLM never reaches
        # here, so it is exempt by construction (D4).
        _budget_add(budget_usage, response.usage)
        _layered_budget_add(
            layered_store,
            layered_keys,
            getattr(response.usage, "prompt_tokens", 0),
            getattr(response.usage, "completion_tokens", 0),
        )
        models_to_try = [model_used]  # stick with the winning model for subsequent turns
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump())  # dict for JSON serializability (session persistence)

        if choice.finish_reason != "tool_calls":
            break

        # AR3 three-phase (D1): plan (serial, original order) → execute (parallel,
        # gather preserves order, batched by D7 cap, D5 same-container serialized) →
        # backfill (serial, original order). N=1 collapses to a single slot dispatched
        # and backfilled identically to the prior sequential path.
        slots = await _plan_run_slots(
            list(msg.tool_calls or []),
            state=state,
            loop_checker=loop_checker,
            guardrail_threshold=guardrail_threshold,
            is_sub_agent=is_sub_agent,
            reply_func=reply_func,
            user_id=user_id,
            session_id=session_id,
        )
        pending = [s for s in slots if s.placeholder is None]
        results = await _execute_pending(
            pending,
            is_sub_agent=is_sub_agent,
            token=token,
            tool_context=tool_context,
            user_id=user_id,
            parallel_max=parallel_max,
            default_tool_timeout=default_tool_timeout,
        )
        _backfill_slots(slots, results, messages=messages, state=state, loop_checker=loop_checker)

    reply = (msg.content if msg is not None else None) or ""
    budget_dimension: str | None = None
    budget_scope: str | None = None
    if stop_reason == StopReason.budget_exceeded:
        # Grace Call (D3): a final summarizing call instead of a hard cut. Its own
        # usage is NOT folded into budget_usage (D4/D6: it spends the reserved
        # dimension). Failure degrades to the partial reply already accumulated.
        budget_dimension = budget_checker.triggered_dimension
        # AR18: a layered (cross-run) scope may be the trigger instead of the
        # per-run AR2 budget; record the scope and its dimension for the trace.
        if layered_checker is not None and layered_checker.triggered_scope is not None:
            budget_scope = layered_checker.triggered_scope
            budget_dimension = budget_dimension or layered_checker.triggered_dimension
        reply = await _grace_call(
            client, cfg, messages, schemas, [model_used], budget_config.max_tokens, reply
        )
    usage = response.usage if response else None
    user_input = _first_user_input(messages)
    _save_flap_state(session_id, flap_state)
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
        budget_dimension=budget_dimension,
        budget_scope=budget_scope,
    )
    # Class-A wiring: completion trace event (model + token usage). Best-effort.
    try:
        _record_agent_run_completed(
            run_id=run_id,
            user_input=user_input,
            reply=reply,
            messages=messages,
            elapsed_s=time.monotonic() - start,
            usage=usage,
            model_used=model_used,
            user_id=user_id,
            agent_name=agent_name,
        )
    except Exception as exc:  # noqa: BLE001 — completion trace is auxiliary
        logger.debug("agent_run_completed_trace_skipped", error=str(exc))
    # Memory extraction unified onto intelligence/memory (class C). Best-effort and
    # awaited (same blocking profile as the prior inline extract_and_save).
    try:
        await extract_and_update(user_id, messages)
    except Exception as exc:  # noqa: BLE001 — memory extraction is auxiliary
        logger.debug("memory_extraction_skipped", error=str(exc))
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
    # AR7: load enabled plugins each CLI invocation, mirroring scan_skills (so a
    # freshly added plugin is picked up). The CLI passes no allowed_tools, so
    # plugin tools are exposed un-gated here — consistent with how the CLI exposes
    # all builtin tools (no per-agent authorization on the CLI path).
    from fleetent.tools.plugin_loader import load_plugins

    load_plugins()
    skills_catalog = available_skills_prompt()
    disabled_trace = collect_disabled_trace() or None

    messages = _assemble_prompt(
        system_prompt, skills_catalog, {"role": "user", "content": user_input}
    )

    async def _run() -> str:
        # SB3: resolve the effective mode (one-time Docker probe, cached) inside the
        # CLI's own event loop so run_code's schema visibility is gated for the CLI too.
        from fleetent.integrations.sandbox import get_effective_mode

        sandbox_mode = await get_effective_mode()
        return await run(
            messages,
            user_id=user_id,
            system_prompt=system_prompt,
            disabled_skills_trace=disabled_trace,
            sandbox_mode=sandbox_mode,
        )

    return asyncio.run(_run())


async def run_stream(
    user_input: str,
    user_id: str = "default",
    system_prompt: str = _SYSTEM,
    allowed_tools: list[str] | None = None,
    agent_name: str | None = None,
    max_turns: int | None = None,
    max_consecutive_failures: int | None = None,
    max_tokens: int | None = None,
    images: list[tuple[bytes, str]] | None = None,
    force_model: str | None = None,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
    guardrail_repeat_threshold: int | None = None,
    cancel_token: CancelToken | None = None,
    sandbox_mode: Mode | None = None,
    agent_features: dict[str, Any] | None = None,
    session_id: str | None = None,
    allowed_skills: list[str] | None = None,
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
    # agent-skill-scoping: narrow the catalog to the agent's allowed_skills (empty /
    # None = no narrowing, all enabled skills visible).
    skills_catalog = available_skills_prompt(allowed_skills=allowed_skills)
    disabled_trace = collect_disabled_trace() or None

    # SB3 D5: execution-time context channel (session/agent/features) for opt-in tools.
    tool_context = ToolContext(
        agent_name=agent_name, features=agent_features or {}, session_id=session_id
    )

    if images:
        user_msg = build_message_with_images(user_input, images)
    else:
        user_msg = {"role": "user", "content": user_input}
    messages: list[Any] = _assemble_prompt(system_prompt, skills_catalog, user_msg)

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
    run_id = str(uuid.uuid4())
    # Class-A wiring (streaming): inject long-term context + record injected-context
    # trace. Best-effort — missing DB / disabled KB must not break the stream.
    try:
        built_context = await build_context(user_id, user_input, agent_name or "", cfg.max_tokens)
        _append_system_context(messages, system_prompt, built_context.text)
        _record_injected_context(run_id, built_context.sources)
    except Exception as exc:  # noqa: BLE001 — long-term context is auxiliary
        logger.debug("long_term_context_skipped", error=str(exc))
    reply = ""
    # MCP4: stop up front when a bound strict MCP server is unavailable (see run()).
    strict_blocked = _strict_blocked_servers(allowed_tools)
    if strict_blocked:
        reply = _strict_unavailable_reply(strict_blocked)
        yield {"type": "text_delta", "content": reply}
        log_run(
            _first_user_input(messages),
            reply,
            messages,
            time.monotonic() - start,
            None,
            user_id=user_id,
            agent_name=agent_name,
            stop_reason=StopReason.mcp_strict_unavailable,
        )
        yield {"type": "done", "content": reply}
        return
    models_to_try = [cfg.model] if force_model is not None else [cfg.model, *cfg.fallbacks]
    model_used = cfg.model
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cache_tokens: dict[str, int] | None = None

    token = cancel_token if cancel_token is not None else CancelToken()
    budget_config = _resolve_budget_config(max_turns, max_tokens)
    budget_usage = BudgetUsage()
    controller, loop_checker, budget_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=False,
        budget_config=budget_config,
        budget_usage=budget_usage,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
        cancel_token=token,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}
    guardrail_threshold = _resolve_guardrail_threshold(guardrail_repeat_threshold)
    parallel_max = _resolve_parallel_max()
    default_tool_timeout = _resolve_default_tool_timeout()
    flap_state = _load_flap_state(session_id)
    layered_checker, layered_store, layered_keys = _setup_layered_budget(
        session_id, user_id, agent_name
    )
    if layered_checker is not None:
        controller.register(layered_checker)

    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break
        state.turn += 1
        messages, flap_state = _gated_compress(
            messages, flap_state, session_id=session_id, user_id=user_id, agent_name=agent_name
        )
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
        # SB3 D1: code-execution enablement point, mirroring run().
        stream_schemas = _filter_code_execution(stream_schemas, sandbox_mode, agent_features)

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
        turn_prompt_tokens = 0
        turn_completion_tokens = 0
        async for chunk in stream:
            if chunk.usage:
                turn_prompt_tokens += chunk.usage.prompt_tokens
                turn_completion_tokens += chunk.usage.completion_tokens
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

        # D1: settle this turn's usage into the per-run accumulator now (step +
        # tokens), so the BudgetChecker judges between turns rather than only
        # at the end of the whole run. Compression's LLM never reaches here (D4).
        budget_usage.add(turn_prompt_tokens, turn_completion_tokens)
        _layered_budget_add(layered_store, layered_keys, turn_prompt_tokens, turn_completion_tokens)

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

        # AR3 + D8 three-phase: yield tool_call events in original order while
        # planning (serial guardrail), execute pending in parallel (gather preserves
        # order, D7-batched, D5-serialized), then yield tool_result events + backfill
        # tool messages strictly in original order — never completion order.
        slots: list[_PlanSlot] = []
        for tc_data in tool_calls_list:
            func: dict[str, str] = tc_data["function"]
            name = func["name"]
            args = func["arguments"]
            yield {"type": "tool_call", "name": name, "args": args}
            tc_fp = arg_fingerprint(args, loop_checker.ignore_arg_keys)
            action = evaluate_guardrail(state, name, tc_fp, guardrail_threshold)
            if action is not GuardrailAction.proceed:
                if action is GuardrailAction.short_circuit:
                    state.loop_warning_injected = True
                else:
                    state.guardrail_tripped = True
                slots.append(
                    _PlanSlot(
                        tc_id=tc_data["id"],
                        name=name,
                        tc_fp=tc_fp,
                        placeholder=(_GUARDRAIL_FEEDBACK_TEXT, False),
                        counts_failure=False,
                    )
                )
                continue
            slots.append(
                _PlanSlot(
                    tc_id=tc_data["id"],
                    name=name,
                    tc_fp=tc_fp,
                    args=args,
                    resource_key=_resource_key(name, session_id),
                )
            )
        pending = [s for s in slots if s.placeholder is None]
        results = await _execute_pending(
            pending,
            is_sub_agent=False,
            token=token,
            tool_context=tool_context,
            user_id=user_id,
            parallel_max=parallel_max,
            default_tool_timeout=default_tool_timeout,
        )
        for slot in slots:
            content, failed = (
                slot.placeholder if slot.placeholder is not None else results[slot.tc_id]
            )
            if slot.counts_failure:
                state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
            yield {"type": "tool_result", "name": slot.name, "content": content}
            # T4: truncate the messages copy only; the SSE event above kept the full result.
            tool_content = (
                content if is_self_truncating(slot.name) else truncate_tool_result(content)
            )
            messages.append({"role": "tool", "tool_call_id": slot.tc_id, "content": tool_content})
            state.record_tool_call(
                slot.name,
                slot.tc_fp,
                result_digest(content),
                not failed,
                window=loop_checker.window,
            )

    budget_dimension: str | None = None
    budget_scope: str | None = None
    if stop_reason == StopReason.budget_exceeded:
        # D7: streaming Grace Call — re-issue one streaming LLM call under the
        # reserved token cap and stream its summary out as text_delta before done.
        # Degradations: (a) failure before any delta → emit the partial reply text
        # then done; (b) failure after partial deltas → keep what streamed (cannot
        # be unsent), record degradation, then done. Both always reach `done`.
        budget_dimension = budget_checker.triggered_dimension
        if layered_checker is not None and layered_checker.triggered_scope is not None:
            budget_scope = layered_checker.triggered_scope
            budget_dimension = budget_dimension or layered_checker.triggered_dimension
        partial_reply = reply
        grace_messages = [*messages, {"role": "user", "content": _GRACE_CALL_TEXT}]
        reserved = grace_max_tokens(budget_config.max_tokens)
        grace_parts: list[str] = []
        any_delta = False
        try:
            grace_stream = await client.chat.completions.create(
                model=model_used,
                messages=grace_messages,
                tools=[],
                max_tokens=reserved,
                stream=True,
                stream_options={"include_usage": True},
                **cfg.params,
            )
            grace_stream = cast(AsyncStream[ChatCompletionChunk], grace_stream)
            async for chunk in grace_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    any_delta = True
                    grace_parts.append(delta.content)
                    yield {"type": "text_delta", "content": delta.content}
            reply = "".join(grace_parts) or partial_reply
        except Exception as exc:  # degrade, never crash the stream (D7)
            if any_delta:
                logger.warning("grace_stream_failed_after_partial", error=str(exc))
                reply = "".join(grace_parts)
            else:
                logger.warning("grace_stream_failed_before_delta", error=str(exc))
                reply = partial_reply
                if partial_reply:
                    yield {"type": "text_delta", "content": partial_reply}

    yield {"type": "done", "content": reply}

    from openai.types import CompletionUsage as _CU  # noqa: N814 — terse local alias

    stream_usage: _CU | None = (
        _CU(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )
        if total_prompt_tokens or total_completion_tokens
        else None
    )
    _save_flap_state(session_id, flap_state)
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
        budget_dimension=budget_dimension,
        budget_scope=budget_scope,
    )
    # Class-A wiring (streaming): completion trace event. Best-effort.
    try:
        _record_agent_run_completed(
            run_id=run_id,
            user_input=user_input,
            reply=reply,
            messages=messages,
            elapsed_s=time.monotonic() - start,
            usage=stream_usage,
            model_used=model_used,
            user_id=user_id,
            agent_name=agent_name,
        )
    except Exception as exc:  # noqa: BLE001 — completion trace is auxiliary
        logger.debug("agent_run_completed_trace_skipped", error=str(exc))
    # Memory extraction unified onto intelligence/memory (class C). Best-effort and
    # awaited (same blocking profile as the prior inline extract_and_save).
    try:
        await extract_and_update(user_id, messages)
    except Exception as exc:  # noqa: BLE001 — memory extraction is auxiliary
        logger.debug("memory_extraction_skipped", error=str(exc))
