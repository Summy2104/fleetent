"""Hook engine (P1): registry + ordered dispatch with isolation and timeout.

Run-time extension points. Operators register in-process Python callbacks via
``@hook(event)`` (loaded from agent-local plugin packages, registered as an import
side-effect like ``@tool``); the agent loop calls ``dispatch(event, ctx)`` at defined
junctures. Pure mechanism — this module imports nothing from the loop, governance, or
tools, so it can be unit-tested by feeding a HookContext and asserting the HookResult.

Security/stance: in-process Python only (never shell), agent-local, error-isolated and
timeout-bounded so a buggy/hung hook can never break or stall a run. See
docs/hooks-system-design-decisions.md.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.hooks")

HookFn = Callable[["HookContext"], "HookResult | None | Coroutine[Any, Any, HookResult | None]"]


@dataclass(frozen=True)
class HookContext:
    """Read-only run context + event-specific payload handed to each hook."""

    event: str
    session_id: str | None
    agent_name: str | None
    user_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """A hook's effect. ``None`` (no return) means proceed / unchanged.

    Fields are honored only at hook points that allow the corresponding capability
    (e.g. ``modified_args`` only at ``pre_tool_use``); see the design doc's matrix.
    """

    decision: Literal["proceed", "deny", "ask"] | None = None
    reason: str | None = None
    modified_args: dict[str, Any] | None = None
    modified_content: str | None = None
    inject_context: str | None = None


# event -> ordered list of hook callbacks. Module-level; reset()/monkeypatch-able in
# tests; never depends on platform.
_registry: dict[str, list[HookFn]] = {}


def hook(event: str) -> Callable[[HookFn], HookFn]:
    """Register ``fn`` as a hook for ``event`` (decorator; sync or async fn)."""

    def deco(fn: HookFn) -> HookFn:
        _registry.setdefault(event, []).append(fn)
        return fn

    return deco


def reset() -> None:
    """Test hook: drop all registrations."""
    _registry.clear()


def has_hooks(event: str) -> bool:
    """Whether any hook is registered for ``event`` (lets callers skip with zero cost)."""
    return bool(_registry.get(event))


async def _run_one(fn: HookFn, ctx: HookContext, timeout: float) -> HookResult | None:
    """Run one hook under a timeout. Sync hooks run in a thread so a slow/blocking
    hook still honors the deadline and never blocks the event loop."""
    if inspect.iscoroutinefunction(fn):
        coro: Coroutine[Any, Any, HookResult | None] = fn(ctx)
    else:
        coro = asyncio.to_thread(fn, ctx)  # type: ignore[arg-type]
    return await asyncio.wait_for(coro, timeout)


async def dispatch(
    event: str,
    ctx: HookContext,
    *,
    timeout: float = 5.0,
    strict: bool = False,
) -> HookResult:
    """Run all hooks for ``event`` in registration order; return the merged result.

    Decision points short-circuit on the first ``deny`` (deny-wins). Transform points
    chain: each hook's ``modified_args``/``modified_content`` is folded back into the
    context so the next hook sees it. A hook that raises or times out is logged and
    skipped (``open``); under ``strict`` a decision-point failure becomes ``deny``
    (fail-closed). Never raises into the caller.
    """
    merged = HookResult()
    for fn in list(_registry.get(event, [])):
        try:
            result = await _run_one(fn, ctx, timeout)
        except Exception as exc:  # noqa: BLE001 — a hook must never break the run
            _logger.warn("hook_failed", event=event, exception=exc)
            if strict:
                return HookResult(decision="deny", reason=f"hook error: {exc}")
            continue
        if result is None:
            continue
        if result.decision == "deny":
            return result  # first-deny-wins
        if result.modified_args is not None:
            ctx = replace(ctx, payload={**ctx.payload, "tool_args": result.modified_args})
            merged.modified_args = result.modified_args
        if result.modified_content is not None:
            ctx = replace(ctx, payload={**ctx.payload, "content": result.modified_content})
            merged.modified_content = result.modified_content
        if result.inject_context is not None:
            merged.inject_context = (merged.inject_context or "") + result.inject_context
        if result.decision == "ask":
            merged.decision = "ask"
            merged.reason = result.reason
    return merged
