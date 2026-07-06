"""Step executors: tool / agent / notify.

Each executor renders its ``${...}`` fields against the run context (fail-closed
on unresolvable references), runs the step through the reused fleetent primitive
(``tools.dispatch`` / ``loop.run`` / outbound delivery), and returns a
``StepResult``. Governance is never bypassed: a tool step is gated the same way
the agent loop gates a tool call, and M1 fails closed on any non-DIRECT
disposition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fleetent.structured_logging import get_logger
from fleetent.workflow import delivery
from fleetent.workflow.definition import StepDef
from fleetent.workflow.errors import WorkflowMappingError
from fleetent.workflow.mapping import render

logger = get_logger("workflow_steps")


@dataclass
class StepContext:
    """Execution context shared by all steps of one run."""

    run_id: str
    agent_name: str | None = None
    principal: Any = None
    origin: dict[str, Any] | None = None
    cancel_token: Any = None
    outbound_connectors: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    status: str  # "succeeded" | "failed"
    output: dict[str, Any] | None = None
    error: str | None = None


async def execute_step(step: StepDef, context: dict[str, Any], ctx: StepContext) -> StepResult:
    """Render and execute a step; unresolvable mappings fail the step (fail-closed)."""
    try:
        if step.type == "tool":
            return await _run_tool(step, context, ctx)
        if step.type == "agent":
            return await _run_agent(step, context, ctx)
        if step.type == "notify":
            return await _run_notify(step, context, ctx)
        return StepResult("failed", error=f"unknown step type {step.type!r}")
    except WorkflowMappingError as exc:
        return StepResult("failed", error=f"mapping error: {exc}")


# ── tool ──────────────────────────────────────────────────────────────────────


async def _run_tool(step: StepDef, context: dict[str, Any], ctx: StepContext) -> StepResult:
    from fleetent.governance.action_gate import ActionMode, resolve_action_mode
    from fleetent.tools import registry
    from fleetent.tools.registry import ToolContext

    assert step.tool is not None
    rendered_args = render(step.args, context)

    tool_context = ToolContext(
        agent_name=ctx.agent_name,
        principal=ctx.principal,
        run_id=ctx.run_id,
        outbound_connectors=ctx.outbound_connectors,
    )

    # Governance: same risk evaluation as the loop. M1 fails closed — only a DIRECT
    # disposition executes; medium/high/critical/sandbox all resolve to non-DIRECT and fail.
    risk = registry.evaluate_risk_level(step.tool, rendered_args, tool_context)
    mode = resolve_action_mode(
        risk, medium_mode="approval", high_mode="approval", sandbox_capable=False, force_ask=False
    )
    if mode is not ActionMode.DIRECT:
        return StepResult(
            "failed",
            error=(
                f"tool {step.tool!r} requires {mode.value} disposition (risk={risk}); "
                "M1 workflow tool steps only run DIRECT tools — wrap it in an agent step "
                "or wait for approval wiring (M2)"
            ),
        )

    user_id = getattr(ctx.principal, "user_id", None)
    try:
        dispatched = registry.dispatch(
            step.tool,
            rendered_args,
            cancel_token=ctx.cancel_token,
            tool_context=tool_context,
            user_id=user_id,
        )
        result = dispatched if isinstance(dispatched, str) else await dispatched
    except Exception as exc:  # noqa: BLE001 — a tool failure fails the step, never crashes the run
        return StepResult("failed", error=f"tool {step.tool!r} raised: {exc}")

    return StepResult("succeeded", output=_coerce_output(result))


def _coerce_output(result: Any) -> dict[str, Any]:
    """A tool returns a string; parse JSON to an object, else wrap as {"text": ...}."""
    if isinstance(result, dict):
        return result
    text = result if isinstance(result, str) else str(result)
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {"text": text}
    return parsed if isinstance(parsed, dict) else {"text": text}


# ── agent ─────────────────────────────────────────────────────────────────────


async def _run_agent(step: StepDef, context: dict[str, Any], ctx: StepContext) -> StepResult:
    from fleetent.runtime import loop as agent_loop
    from fleetent.runtime.snapshot import load_active

    assert step.prompt is not None
    prompt = render(step.prompt, context)

    if step.agent is not None:
        snapshot = load_active(step.agent)
        if snapshot is None:
            return StepResult("failed", error=f"agent {step.agent!r} not found")
        messages = [
            {"role": "system", "content": snapshot.system_prompt},
            {"role": "user", "content": prompt},
        ]
        run_kwargs: dict[str, Any] = {
            "allowed_tools": snapshot.allowed_tools,
            "agent_name": step.agent,
            "model_policy": snapshot.model_policy,
        }
    else:
        messages = [{"role": "user", "content": prompt}]
        run_kwargs = {"agent_name": ctx.agent_name}

    reply = await _run_agent_once(agent_loop, messages, ctx, run_kwargs)
    if not (reply or "").strip():
        # run() returns "" on awaiting_approval (and other abnormal stops). M1 fails closed:
        # an empty agent output is treated as failure rather than propagating nothing downstream.
        return StepResult(
            "failed",
            error="agent produced no output (possibly awaiting approval; M1 does not suspend)",
        )

    if step.output_schema is not None:
        return await _agent_structured(agent_loop, step, messages, reply, ctx, run_kwargs)
    return StepResult("succeeded", output={"text": reply})


async def _run_agent_once(
    agent_loop: Any, messages: list[dict[str, Any]], ctx: StepContext, run_kwargs: dict[str, Any]
) -> str:
    reply: str = await agent_loop.run(
        messages,
        principal=ctx.principal,
        is_sub_agent=True,
        cancel_token=ctx.cancel_token,
        **run_kwargs,
    )
    return reply


async def _agent_structured(
    agent_loop: Any,
    step: StepDef,
    messages: list[dict[str, Any]],
    reply: str,
    ctx: StepContext,
    run_kwargs: dict[str, Any],
) -> StepResult:
    """Enforce output_schema: parse+validate, one corrective retry, else fall back to {text}."""
    assert step.output_schema is not None
    parsed = _parse_schema_output(reply, step.output_schema)
    if parsed is not None:
        return StepResult("succeeded", output=parsed)

    corrective = list(messages) + [
        {"role": "assistant", "content": reply},
        {
            "role": "user",
            "content": (
                "Your reply must be a single JSON object matching this schema and nothing "
                f"else: {json.dumps(step.output_schema, ensure_ascii=False)}"
            ),
        },
    ]
    retry = await _run_agent_once(agent_loop, corrective, ctx, run_kwargs)
    parsed = _parse_schema_output(retry, step.output_schema)
    if parsed is not None:
        return StepResult("succeeded", output=parsed)
    # Two failures: keep the last raw text; a downstream field mapping onto a schema field
    # will then fail closed rather than silently receiving wrong data.
    return StepResult("succeeded", output={"text": retry or reply})


def _parse_schema_output(reply: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    try:
        parsed = json.loads(reply)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    for req in schema.get("required", []):
        if req not in parsed:
            return None
    return parsed


# ── notify ────────────────────────────────────────────────────────────────────


async def _run_notify(step: StepDef, context: dict[str, Any], ctx: StepContext) -> StepResult:
    assert step.text is not None
    text = render(step.text, context)
    to = render(step.to, context) if step.to is not None else None
    target = delivery.resolve_target(to, ctx.origin)
    if target is None:
        return StepResult("failed", error="notify step has no resolvable delivery target")
    error = await delivery.send(target, text, ctx.outbound_connectors)
    if error is not None:
        return StepResult("failed", error=f"notify delivery failed: {error}")
    return StepResult(
        "succeeded", output={"delivered": True, "platform": target[0], "target": target[1]}
    )
