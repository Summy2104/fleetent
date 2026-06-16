"""Core agent loop: send → tool_calls? → dispatch → repeat → final reply."""

import asyncio
import inspect
import json
import random
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, cast

from openai import APIStatusError, AsyncOpenAI, AsyncStream, RateLimitError
from openai.types.chat import ChatCompletionChunk

import fleetent.tools  # noqa: F401  # side-effect: register built-in tools
from fleetent import agent_config
from fleetent.eval_logger import log_run
from fleetent.governance.action_gate import ActionMode, is_sandbox_backed, resolve_action_mode
from fleetent.governance.agent_policy import check_tool_access, is_tool_visible
from fleetent.governance.permission_gate import _default_gate
from fleetent.identity import Principal
from fleetent.integrations.sandbox import Mode, is_code_execution_enabled, redact_secrets
from fleetent.long_term_ctx import ContextSource, build_context
from fleetent.memory import extract_and_update
from fleetent.model import ModelConfigError, ModelPolicySnapshot, ResolvedModelConfig
from fleetent.model.provider_health import ProviderHealthCache, get_health_cache
from fleetent.observability import (
    InjectedContextTrace,
    TraceEvent,
    build_tool_args_summary,
    record_injected_context,
    record_tool_call,
    record_trace_event,
)
from fleetent.outbound import ConversationAddress
from fleetent.runtime.budget import BudgetChecker, BudgetConfig, BudgetUsage, grace_max_tokens
from fleetent.runtime.cancellation import CancellationChecker, CancelToken
from fleetent.runtime.context import (
    AntiFlapState,
    apply_anti_flap,
    compress_for_context_overflow,
    estimate_tokens,
    load_anti_flap_state,
    maybe_compress,
    save_anti_flap_state,
)
from fleetent.runtime.error_classifier import classify
from fleetent.runtime.loop_detector import LoopDetectionChecker, arg_fingerprint, result_digest
from fleetent.runtime.message_hygiene import HygieneReport, MessageContractError, sanitize
from fleetent.runtime.snapshot import GovernanceConfig
from fleetent.runtime.sub_agent import SubAgentExecutor
from fleetent.runtime.termination import (
    ApprovalRejectedChecker,
    ConsecutiveFailuresChecker,
    GuardrailChecker,
    LoopState,
    StopReason,
    TerminationController,
    resolve_limits,
)
from fleetent.runtime.tool_guardrails import GuardrailAction, evaluate_guardrail
from fleetent.session import manager as session_mgr
from fleetent.skills import available_skills_prompt, collect_disabled_trace
from fleetent.skills import match as match_skill  # noqa: F401  # patch target + API parity
from fleetent.skills import scan as scan_skills
from fleetent.structured_logging import get_logger
from fleetent.tools.multimodal import build_message_with_images, has_image_block
from fleetent.tools.registry import (
    ToolContext,
    dispatch,
    evaluate_risk_level,
    get_effective_timeout,
    get_risk_level,
    get_schemas,
    is_self_truncating,
)
from fleetent.tools.result_truncation import truncate_tool_result

_logger = get_logger("runtime.loop")

_SYSTEM = "You are a helpful assistant with access to tools. Use them when needed."

_SUB_AGENT_TOOL = "sub_agent"

ReplyFunc = Callable[[str], Coroutine[Any, Any, None]]
ProgressFunc = Callable[[dict[str, Any]], Awaitable[None]]

# The single code-execution tool gated by the SB3 three-state mode. Filtered out
# of an agent's schema (the one enablement point, D1) when code execution is not
# enabled for that (mode, features) pair.
_RUN_CODE_TOOL = "run_code"


def runtime_sandbox_capable(
    tool_name: str,
    effective_mode: Mode | None,
    *,
    workspace_mount: bool,
) -> bool:
    """Whether a tool call is *actually* contained in the sandbox this run.

    Feeds the action gate's ``sandbox_capable`` input from runtime containment rather
    than a static tool-name lookup (sandbox-containment-gating). A tool is capable
    only when:

    - it is sandbox-backed (``is_sandbox_backed``), AND
    - the effective sandbox mode is not OFF (``None`` is treated as OFF — fail
      closed), AND
    - it really executes inside the container this call. ``run_code`` execs in the
      container whenever the mode is on. The file tools (``read_file`` etc.) instead
      degrade to the host fence when the backend cannot bind-mount the workspace
      (``workspace_mount=False``) — matching ``file_tools._select_backend`` — so they
      are only contained when ``workspace_mount`` is available.

    Args:
        tool_name: The tool call's name (from the server-side registry, not LLM args).
        effective_mode: The run's resolved sandbox mode, or None when unresolved.
        workspace_mount: Whether the active backend bind-mounts the host workspace.

    Returns:
        True iff the tool is structurally isolated in the container for this call.
    """
    if not is_sandbox_backed(tool_name):
        return False
    if effective_mode is None or effective_mode is Mode.OFF:
        return False
    if tool_name == _RUN_CODE_TOOL:
        return True
    # File tools share the host workspace fence (no namespace) when the backend
    # cannot bind-mount, so they are not contained then.
    return workspace_mount


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

# T2-2: appended when the model ends a turn with a blank final reply (finish_reason
# != tool_calls and empty/whitespace content) — nudges weak models to actually answer
# or act instead of returning "". Bounded by _MAX_EMPTY_REPLY_RETRIES so it can't loop.
_MAX_EMPTY_REPLY_RETRIES = 2
_EMPTY_REPLY_CORRECTION = "你的上一条回复是空的。请直接给出最终答案，或调用合适的工具继续完成任务。"

# Appended as a final `user` message when a budget dimension is exhausted (AR2 D3):
# the Grace Call asks the model to summarize progress in one go without further
# tool use, so the user gets a graceful conclusion instead of a half-cut reply.
_GRACE_CALL_TEXT = "已达到本次任务的预算上限。请用一段话总结当前进展与已得结论，不要再调用工具。"


def _limit_config_from_governance(
    governance: GovernanceConfig | None,
) -> dict[str, int] | None:
    """LimitConfig (max_turns / max_consecutive_failures) from governance, or None.

    None lets resolve_limits fall back to its GovernanceConfig-default-backed limits."""
    if governance is None:
        return None
    return {
        "max_turns": governance.agent_max_turns,
        "max_consecutive_failures": governance.agent_max_consecutive_failures,
    }


def _resolve_budget_config(
    max_turns: int | None,
    max_tokens: int | None,
    governance: GovernanceConfig | None = None,
) -> BudgetConfig:
    """Resolve the two-dimensional budget: call param > governance > default.

    The step dimension reuses resolve_limits (seeded from governance); the token
    dimension comes from governance (a default GovernanceConfig when absent)."""
    gov = governance if governance is not None else GovernanceConfig()
    mt, _ = resolve_limits(max_turns, None, config=_limit_config_from_governance(gov))
    if max_tokens is not None:
        return BudgetConfig(max_turns=mt, max_tokens=max_tokens)
    return BudgetConfig(max_turns=mt, max_tokens=gov.agent_max_tokens)


def _resolve_loop_config(
    repeat_threshold: int | None,
    ignore_arg_keys: list[str] | None,
    governance: GovernanceConfig | None = None,
) -> tuple[int, list[str]]:
    """Resolve loop-detection settings: call param > governance > default."""
    if repeat_threshold is not None and ignore_arg_keys is not None:
        return repeat_threshold, ignore_arg_keys
    gov = governance if governance is not None else GovernanceConfig()
    return (
        repeat_threshold if repeat_threshold is not None else gov.agent_loop_repeat_threshold,
        ignore_arg_keys if ignore_arg_keys is not None else list(gov.loop_detect_ignore_arg_keys),
    )


def _resolve_guardrail_threshold(
    guardrail_repeat_threshold: int | None,
    governance: GovernanceConfig | None = None,
) -> int:
    """Resolve the AR10 guardrail threshold: call param > governance > Settings default."""
    if guardrail_repeat_threshold is not None:
        return guardrail_repeat_threshold
    gov = governance if governance is not None else GovernanceConfig()
    return gov.guardrail_repeat_threshold


def _resolve_parallel_max(governance: GovernanceConfig | None = None) -> int:
    """Resolve the AR3 single-round tool concurrency cap: governance > default."""
    gov = governance if governance is not None else GovernanceConfig()
    return gov.agent_tool_parallel_max


def _resolve_default_tool_timeout(governance: GovernanceConfig | None = None) -> float:
    """Global default per-tool timeout: governance > default (T2)."""
    gov = governance if governance is not None else GovernanceConfig()
    return gov.tool_default_timeout_seconds


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


def _append_delivery_trailer(reply: str, tool_context: Any) -> str:
    """Append the run's delivery fact trailer to the final reply, if any (§3, D4).

    The trailer is system-generated from the run's delivery ledger and concatenated AFTER
    the model's text, so the model cannot omit or rewrite it. Empty ledger → reply unchanged
    (zero noise). Best-effort: a render failure never alters the reply."""
    try:
        from fleetent.observability.traces import render_delivery_trailer

        ledger = getattr(tool_context, "delivery_ledger", None)
        trailer = render_delivery_trailer(ledger)
        if trailer:
            return f"{reply}\n\n{trailer}" if reply else trailer
    except Exception as exc:  # noqa: BLE001 — trailer is auxiliary, never break the reply
        _logger.warn("delivery_trailer_failed", error=str(exc))
    return reply


def _resolve_scope_key(session_id: str | None, agent_name: str | None) -> str | None:
    """The workspace scope key for /exchange attribution (D0), mirroring /workspace.

    Reads the process sandbox manager's resolved scope so MCP-produced artifacts are
    keyed exactly like the `/workspace` mount (session_id under `session`, agent_name
    under `agent`). Best-effort: if the manager isn't available (sandbox off / not yet
    built), fall back to session_id so the common (session-scoped) case still attributes.
    """
    try:
        from fleetent.integrations.sandbox.manager import workspace_scope_key
        from fleetent.tools.builtin_tools import _get_manager

        return workspace_scope_key(_get_manager().scope, session_id or "", agent_name or "default")
    except Exception as exc:  # noqa: BLE001 — attribution key is auxiliary, never break the run
        _logger.debug("scope_key_resolve_fell_back_to_session", error=str(exc))
        return session_id


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
            _logger.debug("mcp_degraded_silent", server_id=server_id)
        else:
            _logger.warn("mcp_degraded", server_id=server_id)
    return strict_blocked


def _visible_tool_names(allowed_tools: list[str] | None) -> set[str]:
    """Tool names actually exposed to the model this request — for skill requires_tools.

    Same source + allowed_tools filter the schema list uses, so a skill's
    `requires_tools` is checked against exactly what the agent can call.
    """
    names = {s["function"]["name"] for s in get_schemas()}
    return {n for n in names if is_tool_visible(n, allowed_tools)}


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
        _logger.warn("anti_flap_load_failed", session_id=session_id, error=str(exc))
        return None


def _save_flap_state(session_id: str | None, state: AntiFlapState | None) -> None:
    if not session_id or state is None:
        return
    try:
        save_anti_flap_state(session_id, state)
    except Exception as exc:
        _logger.warn("anti_flap_save_failed", session_id=session_id, error=str(exc))


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


def _build_controller(
    max_turns: int | None,
    max_consecutive_failures: int | None,
    *,
    include_approval: bool,
    budget_config: BudgetConfig,
    run_usage: BudgetUsage,
    loop_repeat_threshold: int | None = None,
    loop_ignore_arg_keys: list[str] | None = None,
    cancel_token: CancelToken | None = None,
    governance: GovernanceConfig | None = None,
) -> tuple[TerminationController, LoopDetectionChecker, BudgetChecker]:
    """Assemble the termination controller with the active checkers.

    The budget checker (AR2) replaces the retired MaxTurnsChecker: the step
    dimension is now one of two budget dimensions (turns / tokens), and
    any exhausted dimension produces `budget_exceeded` (not `max_turns`). The
    `StopReason.max_turns` enum member is retained but the loop no longer produces
    it (design D2). The budget checker reads the same per-run usage tracker the
    loop accumulates into each turn, and is returned so the loop can read the
    triggering dimension for the trace.

    The loop-detection checker (AR4) registers AFTER it so the established
    termination priority (budget / consecutive_failures / approval_rejected) is
    unchanged relative to the old (max_turns / ...) ordering.

    The cancellation checker (AR19) registers first so an already-cancelled token
    short-circuits before any other reason; with a never-cancelling default token
    it can never fire, keeping the no-token path byte-identical.
    """
    _, mcf = resolve_limits(
        max_turns, max_consecutive_failures, config=_limit_config_from_governance(governance)
    )
    threshold, ignore_keys = _resolve_loop_config(
        loop_repeat_threshold, loop_ignore_arg_keys, governance
    )
    controller = TerminationController()
    if cancel_token is not None:
        controller.register(CancellationChecker(cancel_token))
    budget_checker = BudgetChecker(budget_config, run_usage)
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


def _drain_steering(session_id: str | None, messages: list[Any]) -> None:
    """C1: append any mid-run steered user input at the turn boundary.

    Passive consumer of `runtime.steering`: a no-op when there is no session or no
    active steering registration. Called after compression and before sanitize (like
    the loop warning) so injected messages are part of the validated sequence and are
    not swallowed by a same-turn compaction; only ever at a turn boundary, never
    between a tool_call and its result.
    """
    if not session_id:
        return
    from fleetent.runtime import steering

    for text in steering.drain(session_id):
        messages.append({"role": "user", "content": text})


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
            return await asyncio.wait_for(result, timeout=timeout), False
        return cast(str, result), False
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
) -> list[tuple[str, bool, float]]:
    """Dispatch a same-resource-key group strictly in order (D5).

    Same-container stateful tools collapse into one sequential coroutine so the
    batch's gather still sees a single awaitable per group; results stay aligned
    to the group's slot order. T2's configurable default timeout flows to each
    `_safe_dispatch`. Each entry carries the measured dispatch duration in
    milliseconds (trace-tool-spans D1) so backfill can record a tool_call span.
    """
    out: list[tuple[str, bool, float]] = []
    for slot in slots:
        start = time.monotonic()
        if slot.runner is not None:
            content, failed = await slot.runner()
        else:
            content, failed = await _safe_dispatch(
                slot.name,
                slot.args,
                is_sub_agent,
                token,
                tool_context,
                user_id=user_id,
                default_timeout=default_tool_timeout,
            )
        duration_ms = (time.monotonic() - start) * 1000
        out.append((content, failed, duration_ms))
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
) -> tuple[dict[str, tuple[str, bool]], dict[str, float]]:
    """Phase two (D1/D5/D7): run pending slots concurrently, return id→(text,failed)
    plus id→duration_ms (trace-tool-spans D1, for the backfill tool_call span).

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
    durations: dict[str, float] = {}
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
                content, failed, duration_ms = res
                results[slot.tc_id] = (content, failed)
                durations[slot.tc_id] = duration_ms
    return results, durations


async def _plan_run_slots(
    tool_calls: list[Any],
    *,
    state: LoopState,
    loop_checker: LoopDetectionChecker,
    guardrail_threshold: int,
    is_sub_agent: bool,
    reply_func: ReplyFunc | None,
    user_id: str,
    principal: Principal | None = None,
    session_id: str | None,
    governance: GovernanceConfig | None = None,
    agent_name: str | None = None,
    permission_gate_enabled: bool = True,
    permission_gate_medium_timeout: int | None = None,
    permission_gate_high_timeout: int | None = None,
    approval_routing: Any | None = None,
    outbound_connectors: dict[str, Any] | None = None,
    sandbox_effective_mode: Mode | None = None,
    sandbox_workspace_mount: bool = False,
    conversation_address: ConversationAddress | None = None,
    tool_context: ToolContext | None = None,
) -> list[_PlanSlot]:
    """Phase one for run() (D2/D3/D6): serial, original order — produce one slot
    per tool_call. Guardrail, pre_tool_use hook, and (medium/high) approval are decided
    here in order; sub_agent becomes a pending slot whose runner self-gathers (D6). The
    result list preserves original `tool_calls` order so backfill can index 0..N-1.
    """
    from fleetent.runtime import hooks
    from fleetent.runtime.hooks import HookContext

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
                # Identity-port「继承」: sub-agent inherits the parent/turn Principal
                # (full fields incl. tenant_id). Fall back to a user_id-only Principal
                # only on the principal-less standalone baseline.
                inherited_principal = (
                    principal
                    if principal is not None
                    else Principal(user_id=user_id, tenant_id="default")
                )
                sub_results = await SubAgentExecutor().run(
                    tasks=tasks,
                    parent_principal=inherited_principal,
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
        # P1: pre_tool_use hook — decision (deny/ask) + arg rewrite, composed with the
        # existing allowed_tools + permission_gate gate. Zero overhead when hooks are
        # disabled or none registered.
        slot_args: str | dict[str, Any] = tc.function.arguments
        force_ask = False
        if governance is not None and governance.hooks_enabled and hooks.has_hooks("pre_tool_use"):
            parsed = (
                json.loads(tc.function.arguments)
                if isinstance(tc.function.arguments, str)
                else tc.function.arguments
            )
            hres = await hooks.dispatch(
                "pre_tool_use",
                HookContext(
                    event="pre_tool_use",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"tool_name": name, "tool_args": parsed},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=governance.hooks_decision_failure == "strict",
            )
            if hres.decision == "deny":
                slots.append(
                    _PlanSlot(
                        tc_id=tc.id,
                        name=name,
                        tc_fp=tc_fp,
                        placeholder=(
                            f"tool execution denied by policy: {hres.reason or name}",
                            False,
                        ),
                        counts_failure=False,
                    )
                )
                continue
            if hres.modified_args is not None:
                slot_args = hres.modified_args
            force_ask = hres.decision == "ask"
        # Action Gate (C2): the tool's risk maps to a disposition. CRITICAL is hardcoded
        # REJECT; medium/high follow the agent's configured mode (default approval);
        # unknown/uncontainable fail closed upward. Every call is routed through
        # `evaluate_risk_level`, which delegates to `governance.approval_policy.risk_for` —
        # the single authority on the recipient-identity axis. The policy may only RAISE risk
        # on system facts (e.g. send_im_message's recipient ≠ current conversation), never let
        # LLM args lower it below the gate; a broken policy fails closed to medium.
        try:
            _risk_args = json.loads(slot_args) if isinstance(slot_args, str) else slot_args
        except Exception:  # noqa: BLE001 — unparseable args: evaluate with empty mapping
            _risk_args = {}
        risk = evaluate_risk_level(
            name, _risk_args if isinstance(_risk_args, dict) else {}, tool_context
        )
        gate_mode = resolve_action_mode(
            risk,
            medium_mode=(
                governance.action_gate_medium_mode if governance is not None else "approval"
            ),
            high_mode=(governance.action_gate_high_mode if governance is not None else "approval"),
            sandbox_capable=runtime_sandbox_capable(
                name,
                sandbox_effective_mode,
                workspace_mount=sandbox_workspace_mount,
            ),
            force_ask=force_ask,
        )
        if gate_mode is ActionMode.REJECT:
            state.approval_rejected = True
            slots.append(
                _PlanSlot(
                    tc_id=tc.id,
                    name=name,
                    tc_fp=tc_fp,
                    placeholder=(
                        f"tool execution rejected by action gate: {name} (critical risk)",
                        False,
                    ),
                    counts_failure=False,
                )
            )
            continue
        if gate_mode is ActionMode.APPROVAL and reply_func is not None and permission_gate_enabled:
            tool_args = json.loads(slot_args) if isinstance(slot_args, str) else slot_args
            approval_id = str(uuid.uuid4())[:8]
            # D3: approvals are requested serially in original order; only approved
            # tools enter the parallel batch — never concurrent approval prompts.
            decision = await _default_gate.request_approval(
                approval_id=approval_id,
                risk_level=risk if risk in ("medium", "high") else "medium",
                tool_name=name,
                tool_args=tool_args,
                requester_user_id=user_id,
                reply_func=reply_func,
                session_id=session_id or "",
                approval_routing=approval_routing,
                outbound_connectors=outbound_connectors or {},
                medium_timeout=permission_gate_medium_timeout,
                high_timeout=permission_gate_high_timeout,
            )
            if decision == "pending":
                # Suspend (approval-suspend-resume): write a protocol-valid placeholder
                # result and record the pending mapping so the run can end with
                # awaiting_approval and resume later when the human decides.
                state.pending_approvals.append(
                    {
                        "approval_id": approval_id,
                        "tool_call_id": tc.id,
                        "tool_name": name,
                        "tool_args": tool_args,
                        "risk": risk,
                        "approver_ids": sorted(_default_gate.authorized_actors(approval_id)),
                        # conversation-address: persist the run's delivery target so any
                        # resume entry rebuilds an equivalent context (None for non-IM runs).
                        **(
                            {"address": conversation_address.to_dict()}
                            if conversation_address is not None
                            else {}
                        ),
                    }
                )
                slots.append(
                    _PlanSlot(
                        tc_id=tc.id,
                        name=name,
                        tc_fp=tc_fp,
                        placeholder=(f"awaiting_human_approval (id={approval_id})", False),
                        counts_failure=False,
                    )
                )
                continue
            if decision != "approved":
                # Terminal rejection (no approver reachable / default-closed).
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
                args=slot_args,
                resource_key=_resource_key(name, session_id),
            )
        )
    return slots


async def _backfill_slots(
    slots: list[_PlanSlot],
    results: dict[str, tuple[str, bool]],
    *,
    messages: list[Any],
    state: LoopState,
    loop_checker: LoopDetectionChecker,
    governance: "GovernanceConfig | None" = None,
    session_id: str | None = None,
    agent_name: str | None = None,
    user_id: str = "default",
    run_id: str | None = None,
    durations: dict[str, float] | None = None,
) -> None:
    """Phase three (D1/D4): serial, original `tool_calls` order. Append each tool
    message, record the call into the loop-detection window, fold
    `consecutive_failures` per-result — identical to sequential per-tool updates —
    and emit a `tool_call` trace span for each real execution (trace-tool-spans).
    """
    from fleetent.runtime import hooks
    from fleetent.runtime.hooks import HookContext

    for slot in slots:
        placeholder = slot.placeholder
        is_placeholder = placeholder is not None
        content, failed = placeholder if placeholder is not None else results[slot.tc_id]
        if slot.counts_failure:
            state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
        # P2: post_tool_use hook — transform result before it enters messages.
        # Only fires for real tool executions (not placeholder slots from deny/reject).
        if (
            not is_placeholder
            and governance is not None
            and governance.hooks_enabled
            and hooks.has_hooks("post_tool_use")
        ):
            args_val = slot.args
            try:
                parsed_args = json.loads(args_val) if isinstance(args_val, str) else args_val
            except Exception:
                parsed_args = {}
            hres = await hooks.dispatch(
                "post_tool_use",
                HookContext(
                    event="post_tool_use",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={
                        "tool_name": slot.name,
                        "tool_args": parsed_args,
                        "tool_result": content,
                        "failed": failed,
                    },
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if hres.modified_content is not None:
                content = hres.modified_content
        # output-firewall: redact secrets from every real tool result before it reaches
        # the model / persisted session — after the hook (covers its output) and before
        # truncation (so a secret straddling the cap boundary can't leave a fragment).
        # Placeholders are system-authored text with no external secrets, so skip them.
        if not is_placeholder:
            content = redact_secrets(content)
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
        # trace-tool-spans: emit a tool_call span only for real executions — placeholders
        # (guardrail/approval/deny) never reach here as executed work.
        if not is_placeholder:
            _record_tool_call_span(
                run_id=run_id,
                session_id=session_id,
                slot=slot,
                failed=failed,
                duration_ms=(durations or {}).get(slot.tc_id, 0.0),
            )


def _record_tool_call_span(
    *,
    run_id: str | None,
    session_id: str | None,
    slot: _PlanSlot,
    failed: bool,
    duration_ms: float,
) -> None:
    """Record one executed tool call as a tool_call trace span (best-effort)."""
    record_tool_call(
        run_id or "",
        session_id,
        {
            "tool_name": slot.name,
            "tool_call_id": slot.tc_id,
            "args_summary": build_tool_args_summary(slot.args),
            "failed": failed,
            "duration_ms": round(duration_ms, 3),
            "risk": get_risk_level(slot.name),
        },
    )


async def _apply_output_transform(
    reply: str,
    governance: "GovernanceConfig | None",
    session_id: str | None,
    agent_name: str | None,
    user_id: str,
) -> str:
    """P2: output_transform hook — rewrite final reply before it leaves the loop."""
    from fleetent.runtime import hooks
    from fleetent.runtime.hooks import HookContext

    if (
        governance is None
        or not governance.hooks_enabled
        or not hooks.has_hooks("output_transform")
    ):
        return reply
    hres = await hooks.dispatch(
        "output_transform",
        HookContext(
            event="output_transform",
            session_id=session_id,
            agent_name=agent_name,
            user_id=user_id,
            payload={"content": reply},
        ),
        timeout=governance.hooks_timeout_seconds,
        strict=False,
    )
    return hres.modified_content if hres.modified_content is not None else reply


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
    cfg: ResolvedModelConfig,
    messages: list[Any],
    schemas: list[Any],
    model: str,
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
        create_completion = cast(Any, client.chat.completions.create)
        resp = await create_completion(
            model=model,
            messages=grace_messages,
            tools=schemas,
            max_tokens=reserved,
            **cfg.params,
        )
        summary = resp.choices[0].message.content or ""
        if not summary:
            _logger.warn("grace_call_empty_fallback_partial")
            return partial_reply
        return summary
    except Exception as exc:  # degrade to partial result; not swallowed silently
        _logger.warn("grace_call_failed_fallback_partial", error=str(exc))
        return partial_reply


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


def _select_policy_route(messages: list[Any], policy: ModelPolicySnapshot) -> str:
    if not has_image_block(messages):
        return "default"
    if "vision" not in policy.routes:
        raise RuntimeError("消息含图片但未配置 vision 路由，无法处理图片输入")
    return "vision"


def _active_model_policy() -> ModelPolicySnapshot:
    return ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())


def _build_async_client(resolved: ResolvedModelConfig, api_key: str | None) -> AsyncOpenAI:
    if resolved.protocol != "openai_chat":
        raise ModelConfigError(
            f"model route '{resolved.route_key}' target '{resolved.target_id}' "
            f"uses unsupported chat protocol '{resolved.protocol}'"
        )
    if not resolved.base_url:
        raise ModelConfigError(
            f"model route '{resolved.route_key}' target '{resolved.target_id}' missing base_url"
        )
    return AsyncOpenAI(base_url=resolved.base_url, api_key=api_key or "fleetent")


def _model_name(resolved: ResolvedModelConfig) -> str:
    if not resolved.model:
        raise ModelConfigError(
            f"model route '{resolved.route_key}' target '{resolved.target_id}' missing model"
        )
    return resolved.model


async def _call_policy_chat(
    policy: ModelPolicySnapshot,
    chain: tuple[ResolvedModelConfig, ...],
    messages: list[Any],
    schemas: list[Any],
) -> tuple[Any, ResolvedModelConfig]:
    cache = get_health_cache()
    last_exc: Exception | None = None
    candidates = _policy_candidates(chain, cache)
    for i, resolved in enumerate(candidates):
        model = _model_name(resolved)
        is_last = i == len(candidates) - 1
        try:
            api_key = policy.require_api_key(resolved)
            client = _build_async_client(resolved, api_key)
            create_completion = cast(Any, client.chat.completions.create)
            call = partial(
                create_completion,
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=resolved.max_tokens,
                **resolved.params,
            )
            # Retry transient errors (e.g. 429) only on the last/only candidate;
            # earlier candidates fall back immediately, preserving fallback semantics.
            response = await _create_with_transient_retry(call, retry=is_last)
            cache.record_success(model)
            return response, resolved
        except Exception as exc:
            if isinstance(exc, ModelConfigError) or not classify(exc).should_switch_model:
                raise
            cache.record_failure(model)
            last_exc = exc
    raise last_exc  # type: ignore[misc]


async def _stream_policy_chat(
    policy: ModelPolicySnapshot,
    chain: tuple[ResolvedModelConfig, ...],
    messages: list[Any],
    schemas: list[Any],
) -> tuple[Any, ResolvedModelConfig]:
    cache = get_health_cache()
    last_exc: Exception | None = None
    candidates = _policy_candidates(chain, cache)
    for i, resolved in enumerate(candidates):
        model = _model_name(resolved)
        is_last = i == len(candidates) - 1
        try:
            api_key = policy.require_api_key(resolved)
            client = _build_async_client(resolved, api_key)
            create_completion = cast(Any, client.chat.completions.create)
            call = partial(
                create_completion,
                model=model,
                messages=messages,
                tools=schemas,
                max_tokens=resolved.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                **resolved.params,
            )
            stream = await _create_with_transient_retry(call, retry=is_last)
            cache.record_success(model)
            return stream, resolved
        except Exception as exc:
            if isinstance(exc, ModelConfigError) or not classify(exc).should_switch_model:
                raise
            cache.record_failure(model)
            last_exc = exc
    raise last_exc  # type: ignore[misc]


def _policy_candidates(
    chain: tuple[ResolvedModelConfig, ...], cache: ProviderHealthCache
) -> tuple[ResolvedModelConfig, ...]:
    available = tuple(entry for entry in chain if cache.is_available(_model_name(entry)))
    return available or chain


# T2-1: same-target transient-error backoff retry. A transient failure (should_retry
# and not should_compress — e.g. 429) is retried on the SAME target with backoff
# before falling through to model failover. context_overflow (should_compress) is
# excluded (handled by _call_with_overflow_retry).
_MAX_TRANSIENT_RETRIES = 2
_RETRY_BASE_DELAY = 1.0
_RETRY_MAX_DELAY = 30.0


def _retry_after_seconds(exc: Exception) -> float | None:
    """Parse a numeric Retry-After (seconds) header off an APIStatusError, else None.

    The HTTP-date form is not parsed (caller falls back to exponential backoff).
    """
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _backoff_delay(attempt: int, exc: Exception) -> float:
    """Delay before the next same-target retry (attempt is 0-based).

    Respects a Retry-After header when present; otherwise jittered exponential
    backoff capped at `_RETRY_MAX_DELAY`. Patched to 0 in tests.
    """
    after = _retry_after_seconds(exc)
    if after is not None:
        return min(after, _RETRY_MAX_DELAY)
    base = min(_RETRY_BASE_DELAY * (2.0**attempt), _RETRY_MAX_DELAY)
    return base * (0.5 + 0.5 * random.random())  # half-to-full jitter (anti-herd)


async def _create_with_transient_retry(
    do_call: Callable[..., Coroutine[Any, Any, Any]], *, retry: bool = True
) -> Any:
    """Run ``do_call()`` (an awaitable factory), retrying transient errors on the
    same target with backoff (T2-1).

    ``retry=False`` runs a single attempt — used for non-last fallback candidates,
    which fall back immediately on a switchable error rather than retrying. When
    retrying, re-raises on a non-transient error (including context_overflow /
    should_compress) or once the retry cap is reached, so the caller's failover logic
    decides whether to switch target (covers the single/last-provider case where
    there is nothing to fall back to).
    """
    if not retry:
        return await do_call()
    attempt = 0
    while True:
        try:
            return await do_call()
        except Exception as exc:
            cls = classify(exc)
            if (
                isinstance(exc, ModelConfigError)
                or not cls.should_retry
                or cls.should_compress
                or attempt >= _MAX_TRANSIENT_RETRIES
            ):
                raise
            delay = _backoff_delay(attempt, exc)
            _logger.warn(
                "model_transient_retry",
                attempt=attempt + 1,
                delay=round(delay, 2),
                error=str(exc),
            )
            await asyncio.sleep(delay)
            attempt += 1


# C3b: at most one overflow-driven compression+retry per LLM call. A context that
# does not shrink (no-progress guard) or that overflows again after the cap stops
# here, so an un-shrinkable context cannot loop "compress → still overflow → ...".
_MAX_OVERFLOW_COMPRESSIONS = 1


async def _call_with_overflow_retry(
    policy: ModelPolicySnapshot,
    chain: tuple[ResolvedModelConfig, ...],
    messages: list[Any],
    schemas: list[Any],
    *,
    session_id: str | None,
    user_id: str | None,
    agent_name: str | None,
) -> tuple[Any, ResolvedModelConfig]:
    """Call the LLM; on a context-overflow error, compress in place and retry (C3b).

    Wires the previously-dormant `error_classifier.should_compress` flag +
    `compress_for_context_overflow`: a "context too long" error triggers an
    unconditional compression of `messages` (mutated in place so the caller's list
    stays live) and one retry on the SAME target (context_overflow does not switch
    model). The guard re-raises when compression makes no progress or the retry cap
    is hit, so an un-shrinkable context cannot loop.
    """
    attempts = 0
    while True:
        try:
            return await _call_policy_chat(policy, chain, messages, schemas)
        except Exception as exc:
            if not classify(exc).should_compress or attempts >= _MAX_OVERFLOW_COMPRESSIONS:
                raise
            before = estimate_tokens(messages)
            compressed = compress_for_context_overflow(
                messages, session_id=session_id, user_id=user_id, agent_name=agent_name
            )
            if estimate_tokens(compressed) >= before:
                raise  # no-progress guard: compression did not shrink → do not loop
            messages[:] = compressed
            attempts += 1
            _logger.warn(
                "context_overflow_compressed_retry",
                attempt=attempts,
                tokens_before=before,
                tokens_after=estimate_tokens(messages),
                session_id=session_id,
            )


async def _stream_with_overflow_retry(
    policy: ModelPolicySnapshot,
    chain: tuple[ResolvedModelConfig, ...],
    messages: list[Any],
    schemas: list[Any],
    *,
    session_id: str | None,
    user_id: str | None,
    agent_name: str | None,
) -> tuple[Any, ResolvedModelConfig, list[Any]]:
    """Streaming variant of `_call_with_overflow_retry` (C3b).

    Returns `(stream, active_cfg, messages)`; on overflow the messages are
    compressed into a NEW list, so the caller MUST rebind to the returned list
    (run_stream owns its messages locally). Same no-progress + cap guard. Overflow
    on the streaming path surfaces at stream creation (the 400 before any chunk),
    so no partial output has been emitted when we recover.
    """
    attempts = 0
    current = messages
    while True:
        try:
            stream, cfg = await _stream_policy_chat(policy, chain, current, schemas)
            return stream, cfg, current
        except Exception as exc:
            if not classify(exc).should_compress or attempts >= _MAX_OVERFLOW_COMPRESSIONS:
                raise
            before = estimate_tokens(current)
            compressed = compress_for_context_overflow(
                current, session_id=session_id, user_id=user_id, agent_name=agent_name
            )
            if estimate_tokens(compressed) >= before:
                raise  # no-progress guard
            current = compressed
            attempts += 1
            _logger.warn(
                "context_overflow_compressed_retry_stream",
                attempt=attempts,
                tokens_before=before,
                tokens_after=estimate_tokens(current),
                session_id=session_id,
            )


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


def _record_injected_context(
    run_id: str, sources: list[ContextSource], session_id: str | None = None
) -> None:
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
        session_id=session_id,
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
    session_id: str | None = None,
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
            agent_name=agent_name,
            session_id=session_id,
        )
    )


_active_runs: int = 0


async def run(
    messages: list[dict[str, Any]],
    principal: Principal | None = None,
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
    governance: GovernanceConfig | None = None,
    model_policy: ModelPolicySnapshot | None = None,
    permission_gate_enabled: bool = True,
    permission_gate_medium_timeout: int | None = None,
    permission_gate_high_timeout: int | None = None,
    approval_routing: Any | None = None,
    outbound_connectors: dict[str, Any] | None = None,
    progress_func: ProgressFunc | None = None,
    session_context: Any = None,
    conversation_address: ConversationAddress | None = None,
    delivery_ledger: list[Any] | None = None,
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
    user_id = principal.user_id if principal is not None else "default"

    global _active_runs
    _active_runs += 1
    try:
        return await _run_inner(
            messages=messages,
            user_id=user_id,
            principal=principal,
            system_prompt=system_prompt,
            is_sub_agent=is_sub_agent,
            reply_func=reply_func,
            allowed_tools=allowed_tools,
            agent_name=agent_name,
            max_turns=max_turns,
            max_consecutive_failures=max_consecutive_failures,
            max_tokens=max_tokens,
            force_model=force_model,
            disabled_skills_trace=disabled_skills_trace,
            loop_repeat_threshold=loop_repeat_threshold,
            loop_ignore_arg_keys=loop_ignore_arg_keys,
            guardrail_repeat_threshold=guardrail_repeat_threshold,
            cancel_token=cancel_token,
            sandbox_mode=sandbox_mode,
            agent_features=agent_features,
            session_id=session_id,
            allowed_skills=allowed_skills,
            governance=governance,
            model_policy=model_policy,
            permission_gate_enabled=permission_gate_enabled,
            permission_gate_medium_timeout=permission_gate_medium_timeout,
            permission_gate_high_timeout=permission_gate_high_timeout,
            approval_routing=approval_routing,
            outbound_connectors=outbound_connectors,
            progress_func=progress_func,
            session_context=session_context,
            conversation_address=conversation_address,
            delivery_ledger=delivery_ledger,
        )
    finally:
        _active_runs -= 1


async def _run_inner(
    messages: list[dict[str, Any]],
    user_id: str = "default",
    principal: Principal | None = None,
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
    governance: GovernanceConfig | None = None,
    model_policy: ModelPolicySnapshot | None = None,
    permission_gate_enabled: bool = True,
    permission_gate_medium_timeout: int | None = None,
    permission_gate_high_timeout: int | None = None,
    approval_routing: Any | None = None,
    outbound_connectors: dict[str, Any] | None = None,
    progress_func: ProgressFunc | None = None,
    session_context: Any = None,
    conversation_address: ConversationAddress | None = None,
    delivery_ledger: list[Any] | None = None,
) -> str:
    # Image-bearing messages route to the vision model (D6); raises here if
    # images are present but no vision route is configured, before any LLM call.
    # force_model layers a request-level override onto that route (MR1); when
    # None the call stays byte-identical to task_type routing.
    policy = model_policy or _active_model_policy()
    route = _select_policy_route(messages, policy)
    route_chain = policy.resolve(route)
    if force_model is not None:
        route_chain = (route_chain[0].model_copy(update={"model": force_model}),)
    active_cfg = route_chain[0]

    # Determine effective tool schemas (exclude sub_agent for child agents)
    schemas = (
        [s for s in get_schemas() if s["function"]["name"] != _SUB_AGENT_TOOL]
        if is_sub_agent
        else get_schemas()
    )

    # Filter by agent-level allowed_tools (is_tool_visible also drops opt-in tools
    # like bash_exec under allow-all / bare `*`).
    schemas = [s for s in schemas if is_tool_visible(s["function"]["name"], allowed_tools)]

    # SB3 D1: the single code-execution enablement point — drop run_code from this
    # agent's schema when the (mode, features) pair disables it (alongside the
    # allowed_tools filter above).
    schemas = _filter_code_execution(schemas, sandbox_mode, agent_features)

    # sandbox-containment-gating: read the active backend's bind-mount capability once
    # per run (not per gate decision) so the action gate's sandbox_capable reflects
    # whether file tools truly run in-container this run. Best-effort: a manager build
    # failure must not break the run — degrade to "not mounted" (fail closed to gate).
    try:
        from fleetent.tools.builtin_tools import _get_manager

        sandbox_workspace_mount = _get_manager().backend.capabilities.workspace_mount
    except Exception as exc:  # noqa: BLE001 — capability probe is auxiliary, fail closed
        _logger.debug("sandbox_capability_probe_failed", error=str(exc))
        sandbox_workspace_mount = False

    start = time.monotonic()
    run_id = str(uuid.uuid4())
    # delivery-receipts (§2): run-level ledger collecting every outbound receipt this run,
    # read at finalize to render the fact trailer (§3). A caller may seed it (approval-suspend-
    # resume shares one ledger between the resumed tool execution and this continuation so the
    # trailer confirms the approved send); default None → a fresh ledger.
    delivery_ledger = delivery_ledger if delivery_ledger is not None else []
    # SB3 D5: execution-time context channel for run_code (session/agent/features),
    # injected out-of-band only into tools that opt in; harmless for the rest.
    tool_context = ToolContext(
        agent_name=agent_name,
        features=agent_features or {},
        session_id=session_id,
        scope_key=_resolve_scope_key(session_id, agent_name),
        run_id=run_id,
        delivery_ledger=delivery_ledger,
        session_context=session_context,
        principal=principal,
        outbound_connectors=outbound_connectors or {},
        # send-file-to-conversation: the authoritative delivery address (same one text
        # replies use) so send_file lands the file in the current conversation — channel
        # into that channel, DM into that DM — instead of always the requester's DM.
        conversation_address=conversation_address,
    )
    user_input = _first_user_content(messages)
    # Class-A wiring: inject long-term context (KB + memory) and record the
    # injected-context trace. Best-effort — a missing DB / disabled KB must not
    # break the run (mirrors the sandbox/eval_logger best-effort pattern).
    try:
        built_context = await build_context(
            user_id, user_input, agent_name or "", active_cfg.max_tokens or 4096
        )
        _append_system_context(messages, system_prompt, built_context.text)
        _record_injected_context(run_id, built_context.sources, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 — long-term context is auxiliary
        _logger.debug("long_term_context_skipped", error=str(exc))
    # approval-suspend-resume D6: make the model aware of any outstanding approval so
    # it does not re-propose the same gated tool while one is pending in this session.
    if session_id:
        try:
            _pending = await session_mgr.list_pending_approvals(session_id)
            if _pending:
                _names = ", ".join(
                    sorted({str(e.get("tool_name", "?")) for e in _pending.values()})
                )
                _append_system_context(
                    messages,
                    system_prompt,
                    f"当前有 {len(_pending)} 个工具调用正在等待人工审批（{_names}）。"
                    "在用户批准前不要重复发起同一调用；其它请求可正常处理。",
                )
        except Exception as exc:  # noqa: BLE001 — awareness is auxiliary, never break the run
            _logger.debug("pending_approval_note_skipped", error=str(exc))
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
        reply = await _apply_output_transform(reply, governance, session_id, agent_name, user_id)
        return reply
    response = None
    msg: Any = None
    _msg_content: str = ""
    model_used = _model_name(active_cfg)

    # None → a never-cancelling default token, keeping the no-token path identical.
    token = cancel_token if cancel_token is not None else CancelToken()
    budget_config = _resolve_budget_config(max_turns, max_tokens, governance)
    run_usage = BudgetUsage()
    controller, loop_checker, budget_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=True,
        budget_config=budget_config,
        run_usage=run_usage,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
        cancel_token=token,
        governance=governance,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}
    guardrail_threshold = _resolve_guardrail_threshold(guardrail_repeat_threshold, governance)
    parallel_max = _resolve_parallel_max(governance)
    default_tool_timeout = _resolve_default_tool_timeout(governance)
    flap_state = _load_flap_state(session_id)
    empty_reply_retries = 0  # T2-2: bounded self-correction for blank final replies
    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break

        # In-place content assignment (messages[:] = ...) keeps the caller's list
        # reference live: callers (e.g. im_gateway.normalizer) rely on run() mutating
        # the passed `messages` so session_mgr.save() persists the full conversation.
        # Rebinding (messages = ...) would detach it and lose appended turns.
        # P4: pre_compact hook — inject context before compression.
        from fleetent.runtime import hooks

        if governance is not None and governance.hooks_enabled and hooks.has_hooks("pre_compact"):
            from fleetent.runtime.hooks import HookContext

            _prc = await hooks.dispatch(
                "pre_compact",
                HookContext(
                    event="pre_compact",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"message_count": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if _prc.inject_context is not None:
                messages.append({"role": "user", "content": _prc.inject_context})
        _msgs_before = len(messages)
        _compressed, flap_state = _gated_compress(
            messages, flap_state, session_id=session_id, user_id=user_id, agent_name=agent_name
        )
        messages[:] = _compressed
        # P4: post_compact hook — observe compression outcome.
        if governance is not None and governance.hooks_enabled and hooks.has_hooks("post_compact"):
            from fleetent.runtime.hooks import HookContext as _HCpc

            await hooks.dispatch(
                "post_compact",
                _HCpc(
                    event="post_compact",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"messages_before": _msgs_before, "messages_after": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
        # D4b: inject the loop warning AFTER compression so a same-round compaction
        # cannot swallow it; it must be present in the sequence sent to the LLM.
        _maybe_inject_loop_warning(messages, state)
        # C1: drain mid-run steered input at the turn boundary (before sanitize).
        _drain_steering(session_id, messages)
        try:
            clean, report = sanitize(messages)
        except MessageContractError as exc:
            # Unrepairable sequence: fail locally before the LLM call (design D3).
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            return ""
        messages[:] = clean
        _accumulate_repairs(hygiene_repairs, report)
        # P3: pre_llm_call hook — observe or inject context before each LLM call.
        from fleetent.runtime import hooks

        if governance is not None and governance.hooks_enabled and hooks.has_hooks("pre_llm_call"):
            from fleetent.runtime.hooks import HookContext

            _plc_res = await hooks.dispatch(
                "pre_llm_call",
                HookContext(
                    event="pre_llm_call",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"message_count": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if _plc_res.inject_context is not None:
                messages.append({"role": "user", "content": _plc_res.inject_context})
        try:
            response, active_cfg = await _call_with_overflow_retry(
                policy,
                route_chain,
                messages,
                schemas,
                session_id=session_id,
                user_id=user_id,
                agent_name=agent_name,
            )
            model_used = _model_name(active_cfg)
        except Exception as exc:
            # Record the error class on the trace before propagating (design D4).
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            raise
        state.turn += 1
        # D1: accumulate this turn's usage immediately (step + tokens + cost) so the
        # BudgetChecker judges on up-to-date usage at the next checkpoint — not on a
        # single end-of-loop response.usage. Compression's internal LLM never reaches
        # here, so it is exempt by construction (D4).
        _budget_add(run_usage, response.usage)
        route_chain = (active_cfg,)  # stick with the winning target for subsequent turns
        choice = response.choices[0]
        msg = choice.message
        # P3: on_assistant_reply hook — observe or rewrite text content before it enters messages.
        # Skipped for tool_calls-only turns (msg.content is None/empty, no text to transform).
        _msg_content = msg.content or ""
        if (
            _msg_content
            and governance is not None
            and governance.hooks_enabled
            and hooks.has_hooks("on_assistant_reply")
        ):
            from fleetent.runtime.hooks import HookContext

            _oar_res = await hooks.dispatch(
                "on_assistant_reply",
                HookContext(
                    event="on_assistant_reply",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"content": _msg_content},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if _oar_res.modified_content is not None:
                _msg_content = _oar_res.modified_content
                # Rebuild the message dict with rewritten content.
                _dump = msg.model_dump()
                _dump["content"] = _msg_content
                messages.append(_dump)
            else:
                messages.append(msg.model_dump())
        else:
            messages.append(msg.model_dump())  # dict for JSON serializability

        if choice.finish_reason != "tool_calls":
            # T2-2: a blank final reply (weak models) → nudge once more instead of
            # returning "", bounded by the cap so it cannot loop forever.
            if not (msg.content or "").strip() and empty_reply_retries < _MAX_EMPTY_REPLY_RETRIES:
                empty_reply_retries += 1
                messages.append({"role": "user", "content": _EMPTY_REPLY_CORRECTION})
                continue
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
            principal=principal,
            session_id=session_id,
            governance=governance,
            agent_name=agent_name,
            permission_gate_enabled=permission_gate_enabled,
            permission_gate_medium_timeout=permission_gate_medium_timeout,
            permission_gate_high_timeout=permission_gate_high_timeout,
            approval_routing=approval_routing,
            outbound_connectors=outbound_connectors,
            sandbox_effective_mode=sandbox_mode,
            sandbox_workspace_mount=sandbox_workspace_mount,
            conversation_address=conversation_address,
            tool_context=tool_context,
        )
        pending = [s for s in slots if s.placeholder is None]
        # Progress is emitted once per execution batch (not per tool during planning):
        # carry every in-flight tool name so adapters can show the whole batch rather
        # than only the last. sub_agent runs never surface to the parent's progress.
        if progress_func is not None and not is_sub_agent and pending:
            _names = [s.name for s in pending]
            try:  # noqa: SIM105 — cannot use contextlib.suppress with async await
                await progress_func({"type": "tool_call", "names": _names, "name": _names[0]})
            except Exception:  # noqa: BLE001 — progress feedback must not break the run
                pass
        results, durations = await _execute_pending(
            pending,
            is_sub_agent=is_sub_agent,
            token=token,
            tool_context=tool_context,
            user_id=user_id,
            parallel_max=parallel_max,
            default_tool_timeout=default_tool_timeout,
        )
        await _backfill_slots(
            slots,
            results,
            messages=messages,
            state=state,
            loop_checker=loop_checker,
            governance=governance,
            session_id=session_id,
            agent_name=agent_name,
            user_id=user_id,
            run_id=run_id,
            durations=durations,
        )

        # approval-suspend-resume: a gated tool call wrote an awaiting_human_approval
        # placeholder this turn → suspend the run (non-terminal). The prompt was already
        # sent by the gate; pending state is persisted below for resume.
        if state.pending_approvals:
            stop_reason = StopReason.awaiting_approval
            break

    # Persist pending approvals to the session so resolution can resume after this
    # run returns (and across a process restart). The caller's session save preserves
    # this meta (save(meta=None) merges existing meta).
    if state.pending_approvals and session_id:
        for entry in state.pending_approvals:
            await session_mgr.add_pending_approval(session_id, str(entry["approval_id"]), entry)

    reply = (
        _msg_content
        if (msg is not None and _msg_content)
        else ((msg.content if msg is not None else None) or "")
    )
    budget_dimension: str | None = None
    budget_scope: str | None = None
    if stop_reason == StopReason.budget_exceeded:
        # Grace Call (D3): a final summarizing call instead of a hard cut. Its own
        # usage is NOT folded into the per-run usage tracker (D4/D6: it spends the reserved
        # dimension). Failure degrades to the partial reply already accumulated.
        budget_dimension = budget_checker.triggered_dimension
        reply = await _grace_call(
            _build_async_client(active_cfg, policy.require_api_key(active_cfg)),
            active_cfg,
            messages,
            schemas,
            model_used,
            budget_config.max_tokens,
            reply,
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
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 — completion trace is auxiliary
        _logger.debug("agent_run_completed_trace_skipped", error=str(exc))
    # Memory extraction unified onto intelligence/memory (class C). Best-effort and
    # awaited (same blocking profile as the prior inline extract_and_save).
    try:
        await extract_and_update(user_id, messages, model_policy=policy)
    except Exception as exc:  # noqa: BLE001 — memory extraction is auxiliary
        _logger.debug("memory_extraction_skipped", error=str(exc))
    reply = await _apply_output_transform(reply, governance, session_id, agent_name, user_id)
    # P4: on_run_complete hook — observe after reply is finalized.
    from fleetent.runtime import hooks as _hooks_orc

    if (
        governance is not None
        and governance.hooks_enabled
        and _hooks_orc.has_hooks("on_run_complete")
    ):
        from fleetent.runtime.hooks import HookContext as _HCorc

        await _hooks_orc.dispatch(
            "on_run_complete",
            _HCorc(
                event="on_run_complete",
                session_id=session_id,
                agent_name=agent_name,
                user_id=user_id,
                payload={
                    "reply": reply,
                    "stop_reason_name": stop_reason.name if stop_reason is not None else "normal",
                },
            ),
            timeout=governance.hooks_timeout_seconds,
            strict=False,
        )
    # delivery-receipts (§3): the fact trailer is appended LAST — after on_response hooks —
    # so neither the model nor a hook can omit or rewrite it.
    return _append_delivery_trailer(reply, tool_context)


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
    # file-driven-agent-config: rescan agent.yaml files each CLI invocation so freshly
    # added/edited agents are picked up (mirrors scan_skills).
    agent_config.scan()
    # AR7: load enabled plugins each CLI invocation, mirroring scan_skills (so a
    # freshly added plugin is picked up). The CLI passes no allowed_tools, so
    # plugin tools are exposed un-gated here — consistent with how the CLI exposes
    # all builtin tools (no per-agent authorization on the CLI path).
    from fleetent.tools.plugin_loader import load_plugins

    load_plugins()

    # agent-runtime-cli: apply the deployed home/default agent so the one-shot CLI runs
    # AS that agent (its system_prompt / allowed_tools / allowed_skills), not the generic
    # default. With no deployed agent, fall back to the generic behavior unchanged.
    index = agent_config.current()
    default_name = index.default_agent()
    agent = index.get(default_name) if default_name else None
    allowed_tools: list[str] | None = None
    allowed_skills: list[str] | None = None
    agent_name: str | None = None
    agent_features: dict[str, Any] | None = None
    governance: GovernanceConfig | None = None
    model_policy: ModelPolicySnapshot | None = None
    if agent is not None:
        from fleetent.runtime.snapshot import _governance_from_file
        from fleetent.tools.plugin_loader import expand_plugin_patterns

        if agent.system_prompt:
            system_prompt = agent.system_prompt
        allowed_tools = agent.allowed_tools + expand_plugin_patterns(agent.plugins)
        allowed_skills = agent.allowed_skills
        agent_name = agent.name
        agent_features = agent.features
        governance = _governance_from_file(agent)
        model_policy = ModelPolicySnapshot.from_agent(agent)

    skills_catalog = available_skills_prompt(
        allowed_skills=allowed_skills, available_tools=_visible_tool_names(allowed_tools)
    )
    disabled_trace = collect_disabled_trace() or None

    messages = _assemble_prompt(
        system_prompt, skills_catalog, {"role": "user", "content": user_input}
    )

    async def _run() -> str:
        # SB3: resolve the effective mode (one-time Docker probe, cached) inside the
        # CLI's own event loop so run_code's schema visibility is gated for the CLI too.
        from fleetent.integrations.sandbox import enablement as sandbox_enablement

        sandbox_mode = await sandbox_enablement.get_effective_mode()
        return await run(
            messages,
            principal=Principal(user_id=user_id, tenant_id="default"),
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            agent_name=agent_name,
            agent_features=agent_features,
            allowed_skills=allowed_skills,
            disabled_skills_trace=disabled_trace,
            sandbox_mode=sandbox_mode,
            governance=governance,
            model_policy=model_policy,
        )

    return asyncio.run(_run())


async def run_stream(
    user_input: str,
    principal: Principal | None = None,
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
    governance: GovernanceConfig | None = None,
    model_policy: ModelPolicySnapshot | None = None,
    session_context: Any = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, reasoning_delta, done.
    text_delta events stream as tokens arrive from the LLM; reasoning_delta carries
    a backend reasoning trace (reasoning_content) when present, for display only
    (kept out of the reply and never fed back to the LLM). To request reasoning,
    set reasoning_effort / extra_body.reasoning in the target's params (agent.yaml).

    When `images` (a list of (bytes, mime)) is given, the user message is built
    as a content-block array (text + image_url blocks, base64-inlined) and the
    run routes to the vision model (AR21). Plain-text input is unchanged.

    Termination covers max_turns / consecutive_failures; approval gating is not
    performed on the streaming path, so approval_rejected does not apply here.
    """
    user_id = principal.user_id if principal is not None else "default"

    # agent-skill-scoping: narrow the catalog to the agent's allowed_skills (empty /
    # None = no narrowing, all enabled skills visible).
    skills_catalog = available_skills_prompt(
        allowed_skills=allowed_skills, available_tools=_visible_tool_names(allowed_tools)
    )
    disabled_trace = collect_disabled_trace() or None

    # SB3 D5: execution-time context channel (session/agent/features) for opt-in tools.
    # delivery-receipts (§2): streaming path's run-level ledger; run_id set just below.
    _stream_delivery_ledger: list[Any] = []
    tool_context = ToolContext(
        agent_name=agent_name,
        features=agent_features or {},
        session_id=session_id,
        scope_key=_resolve_scope_key(session_id, agent_name),
        delivery_ledger=_stream_delivery_ledger,
        session_context=session_context,
        principal=principal,
    )

    # P3: on_user_input hook — intercept/rewrite/deny before user message enters messages.
    from fleetent.runtime import hooks

    if governance is not None and governance.hooks_enabled and hooks.has_hooks("on_user_input"):
        from fleetent.runtime.hooks import HookContext

        _hres = await hooks.dispatch(
            "on_user_input",
            HookContext(
                event="on_user_input",
                session_id=session_id,
                agent_name=agent_name,
                user_id=user_id,
                payload={"content": user_input},
            ),
            timeout=governance.hooks_timeout_seconds,
            strict=governance.hooks_decision_failure == "strict",
        )
        if _hres.decision == "deny":
            yield {"type": "error", "content": _hres.reason or "request denied by policy"}
            return
        if _hres.modified_content is not None:
            user_input = _hres.modified_content

    if images:
        user_msg = build_message_with_images(user_input, images)
    else:
        user_msg = {"role": "user", "content": user_input}
    messages: list[Any] = _assemble_prompt(system_prompt, skills_catalog, user_msg)

    # Route to vision when images are present; raises before any LLM call if
    # images are present but no vision route is configured (D6, option A).
    # force_model layers a request-level override (MR1); None keeps task_type
    # routing byte-identical.
    policy = model_policy or _active_model_policy()
    route = _select_policy_route(messages, policy)
    route_chain = policy.resolve(route)
    if force_model is not None:
        route_chain = (route_chain[0].model_copy(update={"model": force_model}),)
    active_cfg = route_chain[0]

    start = time.monotonic()
    run_id = str(uuid.uuid4())
    tool_context.run_id = run_id  # delivery-receipts (§2): bind ledger receipts' trace to this run
    # Class-A wiring (streaming): inject long-term context + record injected-context
    # trace. Best-effort — missing DB / disabled KB must not break the stream.
    try:
        built_context = await build_context(
            user_id, user_input, agent_name or "", active_cfg.max_tokens or 4096
        )
        _append_system_context(messages, system_prompt, built_context.text)
        _record_injected_context(run_id, built_context.sources, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 — long-term context is auxiliary
        _logger.debug("long_term_context_skipped", error=str(exc))
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
        reply = await _apply_output_transform(reply, governance, session_id, agent_name, user_id)
        yield {"type": "done", "content": reply}
        return
    model_used = _model_name(active_cfg)
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cache_tokens: dict[str, int] | None = None

    token = cancel_token if cancel_token is not None else CancelToken()
    budget_config = _resolve_budget_config(max_turns, max_tokens, governance)
    run_usage = BudgetUsage()
    controller, loop_checker, budget_checker = _build_controller(
        max_turns,
        max_consecutive_failures,
        include_approval=False,
        budget_config=budget_config,
        run_usage=run_usage,
        loop_repeat_threshold=loop_repeat_threshold,
        loop_ignore_arg_keys=loop_ignore_arg_keys,
        cancel_token=token,
        governance=governance,
    )
    state = LoopState()
    stop_reason = StopReason.normal
    hygiene_repairs: dict[str, int] = {}
    guardrail_threshold = _resolve_guardrail_threshold(guardrail_repeat_threshold, governance)
    parallel_max = _resolve_parallel_max(governance)
    default_tool_timeout = _resolve_default_tool_timeout(governance)
    flap_state = _load_flap_state(session_id)
    empty_reply_retries = 0  # T2-2: bounded self-correction for blank final replies
    while True:
        forced = controller.should_stop(state)
        if forced is not None:
            stop_reason = forced
            break
        state.turn += 1
        # P4: pre_compact (streaming path)
        from fleetent.runtime import hooks as _hooks_pc

        if (
            governance is not None
            and governance.hooks_enabled
            and _hooks_pc.has_hooks("pre_compact")
        ):
            from fleetent.runtime.hooks import HookContext as _HCprc

            _prc_s = await _hooks_pc.dispatch(
                "pre_compact",
                _HCprc(
                    event="pre_compact",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"message_count": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if _prc_s.inject_context is not None:
                messages.append({"role": "user", "content": _prc_s.inject_context})
        _smb = len(messages)
        messages, flap_state = _gated_compress(
            messages, flap_state, session_id=session_id, user_id=user_id, agent_name=agent_name
        )
        # P4: post_compact (streaming path)
        if (
            governance is not None
            and governance.hooks_enabled
            and _hooks_pc.has_hooks("post_compact")
        ):
            from fleetent.runtime.hooks import HookContext as _HCpoc

            await _hooks_pc.dispatch(
                "post_compact",
                _HCpoc(
                    event="post_compact",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"messages_before": _smb, "messages_after": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
        # D4b: inject the loop warning after compression, before sanitize/LLM call.
        _maybe_inject_loop_warning(messages, state)
        # C1: drain mid-run steered input at the turn boundary (before sanitize).
        _drain_steering(session_id, messages)
        try:
            messages, report = sanitize(messages)
        except MessageContractError as exc:
            yield {"type": "error", "content": str(exc)}
            _log_run_error(exc, messages, start, model_used, user_id, agent_name)
            return
        _accumulate_repairs(hygiene_repairs, report)
        # P3: pre_llm_call hook (streaming path) — inject context before each LLM call.
        from fleetent.runtime import hooks as _hooks_plc

        if (
            governance is not None
            and governance.hooks_enabled
            and _hooks_plc.has_hooks("pre_llm_call")
        ):
            from fleetent.runtime.hooks import HookContext as _HC_plc

            _plc_s = await _hooks_plc.dispatch(
                "pre_llm_call",
                _HC_plc(
                    event="pre_llm_call",
                    session_id=session_id,
                    agent_name=agent_name,
                    user_id=user_id,
                    payload={"message_count": len(messages)},
                ),
                timeout=governance.hooks_timeout_seconds,
                strict=False,
            )
            if _plc_s.inject_context is not None:
                messages.append({"role": "user", "content": _plc_s.inject_context})

        # Accumulate streaming response
        reply_parts: list[str] = []
        # tool_calls_acc: index → {id, name, arguments}
        tool_calls_acc: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        stream_schemas = get_schemas()
        stream_schemas = [
            s for s in stream_schemas if is_tool_visible(s["function"]["name"], allowed_tools)
        ]
        # SB3 D1: code-execution enablement point, mirroring run().
        stream_schemas = _filter_code_execution(stream_schemas, sandbox_mode, agent_features)

        try:
            stream, active_cfg, messages = await _stream_with_overflow_retry(
                policy,
                route_chain,
                messages,
                stream_schemas,
                session_id=session_id,
                user_id=user_id,
                agent_name=agent_name,
            )
            model_used = _model_name(active_cfg)
            route_chain = (active_cfg,)
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

            # C4: surface a backend reasoning trace (reasoning_content; a non-standard
            # delta field on e.g. DeepSeek-R1 / QwQ) so clients can display the thinking.
            # isinstance(str) guards against absent / auto-mocked fields → no-op for
            # standard backends. NOT added to reply text and NOT fed back to the LLM
            # (some backends reject reasoning_content as input), so it stays out of messages.
            reasoning = getattr(delta, "reasoning_content", None)
            if isinstance(reasoning, str) and reasoning:
                yield {"type": "reasoning_delta", "content": reasoning}

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
        run_usage.add(turn_prompt_tokens, turn_completion_tokens)

        if finish_reason != "tool_calls":
            reply = "".join(reply_parts)
            # T2-2: blank final reply → nudge once more (bounded) instead of ending empty.
            if not reply.strip() and empty_reply_retries < _MAX_EMPTY_REPLY_RETRIES:
                empty_reply_retries += 1
                messages.append({"role": "user", "content": _EMPTY_REPLY_CORRECTION})
                continue
            # P3: on_assistant_reply hook on the final text reply.
            # Already-streamed text_delta events are not retractable; only done + output_transform
            # will use the modified reply.
            from fleetent.runtime import hooks as _hooks_oar

            if (
                reply
                and governance is not None
                and governance.hooks_enabled
                and _hooks_oar.has_hooks("on_assistant_reply")
            ):
                from fleetent.runtime.hooks import HookContext as _HookCtx

                _oar = await _hooks_oar.dispatch(
                    "on_assistant_reply",
                    _HookCtx(
                        event="on_assistant_reply",
                        session_id=session_id,
                        agent_name=agent_name,
                        user_id=user_id,
                        payload={"content": reply},
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=False,
                )
                if _oar.modified_content is not None:
                    reply = _oar.modified_content
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
        from fleetent.runtime import hooks
        from fleetent.runtime.hooks import HookContext

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
            # P1: pre_tool_use hook. Streaming has no permission_gate, so `ask`
            # degrades to deny + note. deny → placeholder; modified_args → rewrite.
            slot_args: str | dict[str, Any] = args
            if (
                governance is not None
                and governance.hooks_enabled
                and hooks.has_hooks("pre_tool_use")
            ):
                parsed = json.loads(args) if isinstance(args, str) else args
                hres = await hooks.dispatch(
                    "pre_tool_use",
                    HookContext(
                        event="pre_tool_use",
                        session_id=session_id,
                        agent_name=agent_name,
                        user_id=user_id,
                        payload={"tool_name": name, "tool_args": parsed},
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=governance.hooks_decision_failure == "strict",
                )
                if hres.decision in ("deny", "ask"):
                    note = hres.reason or name
                    if hres.decision == "ask":
                        note = f"需人工确认（流式不支持审批，已拦截）：{note}"
                    slots.append(
                        _PlanSlot(
                            tc_id=tc_data["id"],
                            name=name,
                            tc_fp=tc_fp,
                            placeholder=(f"tool execution blocked by policy: {note}", False),
                            counts_failure=False,
                        )
                    )
                    continue
                if hres.modified_args is not None:
                    slot_args = hres.modified_args
            slots.append(
                _PlanSlot(
                    tc_id=tc_data["id"],
                    name=name,
                    tc_fp=tc_fp,
                    args=slot_args,
                    resource_key=_resource_key(name, session_id),
                )
            )
        pending = [s for s in slots if s.placeholder is None]
        results, durations = await _execute_pending(
            pending,
            is_sub_agent=False,
            token=token,
            tool_context=tool_context,
            user_id=user_id,
            parallel_max=parallel_max,
            default_tool_timeout=default_tool_timeout,
        )
        for slot in slots:
            placeholder = slot.placeholder
            is_placeholder = placeholder is not None
            content, failed = placeholder if placeholder is not None else results[slot.tc_id]
            if slot.counts_failure:
                state.consecutive_failures = state.consecutive_failures + 1 if failed else 0
            # output-firewall: redact before the result is streamed out (the event is not
            # retractable) and before it enters messages. Placeholders are system text.
            if not is_placeholder:
                content = redact_secrets(content)
            yield {"type": "tool_result", "name": slot.name, "content": content}
            # P2: post_tool_use hook, real executions only; SSE already sent (not retractable).
            # modified_content only affects what enters messages (used by the LLM next turn).
            if (
                not is_placeholder
                and governance is not None
                and governance.hooks_enabled
                and hooks.has_hooks("post_tool_use")
            ):
                from fleetent.runtime.hooks import HookContext

                args_val = slot.args
                try:
                    parsed_args = json.loads(args_val) if isinstance(args_val, str) else args_val
                except Exception:
                    parsed_args = {}
                hres = await hooks.dispatch(
                    "post_tool_use",
                    HookContext(
                        event="post_tool_use",
                        session_id=session_id,
                        agent_name=agent_name,
                        user_id=user_id,
                        payload={
                            "tool_name": slot.name,
                            "tool_args": parsed_args,
                            "tool_result": content,
                            "failed": failed,
                        },
                    ),
                    timeout=governance.hooks_timeout_seconds,
                    strict=False,
                )
                if hres.modified_content is not None:
                    # Re-redact: the hook may have reintroduced secrets into the content
                    # that now enters messages (the streamed event already went out clean).
                    content = redact_secrets(hres.modified_content)
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
            # trace-tool-spans: span only for real executions (run_stream parity with run).
            if not is_placeholder:
                _record_tool_call_span(
                    run_id=run_id,
                    session_id=session_id,
                    slot=slot,
                    failed=failed,
                    duration_ms=durations.get(slot.tc_id, 0.0),
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
        partial_reply = reply
        grace_messages = [*messages, {"role": "user", "content": _GRACE_CALL_TEXT}]
        reserved = grace_max_tokens(budget_config.max_tokens)
        grace_parts: list[str] = []
        any_delta = False
        try:
            grace_client = _build_async_client(active_cfg, policy.require_api_key(active_cfg))
            create_completion = cast(Any, grace_client.chat.completions.create)
            grace_stream = await create_completion(
                model=model_used,
                messages=grace_messages,
                tools=[],
                max_tokens=reserved,
                stream=True,
                stream_options={"include_usage": True},
                **active_cfg.params,
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
                _logger.warn("grace_stream_failed_after_partial", error=str(exc))
                reply = "".join(grace_parts)
            else:
                _logger.warn("grace_stream_failed_before_delta", error=str(exc))
                reply = partial_reply
                if partial_reply:
                    yield {"type": "text_delta", "content": partial_reply}

    reply = await _apply_output_transform(reply, governance, session_id, agent_name, user_id)
    # delivery-receipts (§3): after the stream, append the fact trailer as a final delta
    # (separate from the model's text, so it cannot be omitted) and fold it into `done`.
    _with_trailer = _append_delivery_trailer(reply, tool_context)
    if _with_trailer != reply:
        yield {"type": "text_delta", "content": _with_trailer[len(reply) :]}
        reply = _with_trailer
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
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 — completion trace is auxiliary
        _logger.debug("agent_run_completed_trace_skipped", error=str(exc))
    # Memory extraction unified onto intelligence/memory (class C). Best-effort and
    # awaited (same blocking profile as the prior inline extract_and_save).
    try:
        await extract_and_update(user_id, messages, model_policy=policy)
    except Exception as exc:  # noqa: BLE001 — memory extraction is auxiliary
        _logger.debug("memory_extraction_skipped", error=str(exc))
