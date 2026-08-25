"""Plan-and-Execute control strategy (agent-side).

A second turn-level paradigm alongside ReAct: instead of interleaving reason and
act one step at a time, the model plans the whole task up front (a validated
workflow-shaped plan), the plan executes step by step, and a failed step triggers
a bounded *replan*. Control flow here is deterministic Python; the model decides
plan *content*, the code decides plan *shape* and when to replan.

This module writes NO execution engine. It reuses the declarative workflow layer:

- ``workflow.definition.parse_definition`` validates the plan (fields, dep
  existence, placeholder syntax, DAG acyclicity) and returns a frozen ``WorkflowDef``.
- ``workflow.engine.compute_ready`` / ``compute_cascade_skips`` are the pure DAG
  readiness functions that drive execution waves — no SQLite store, no sweep, no
  delivery (those are for standalone declarative workflows; a conversational turn
  needs none of them).
- ``workflow.steps.execute_step`` runs each step (agent sub-run / tool / notify)
  with ``${steps.x.output}`` templating and structured output.

Design contracts:
- Agent-side only. MUST NOT import ``fleetent.platform.*``.
- Injectable ``planner`` / ``synthesizer`` / ``step_runner`` (no global singleton):
  tests pass stubs; production lazily binds the real LLM planner and
  ``execute_step``. The lazy import of ``runtime.loop`` in the default planner
  breaks the loop<->plan_execute import cycle (same pattern as ``sub_agent``).
- Bounded replans: a failed step regenerates only the remaining work, capped by
  ``max_replans`` so a persistently failing plan cannot loop forever.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fleetent.structured_logging import get_logger
from fleetent.workflow.definition import WorkflowDef, parse_definition
from fleetent.workflow.engine import compute_cascade_skips, compute_ready
from fleetent.workflow.errors import WorkflowDefinitionError
from fleetent.workflow.steps import StepContext, StepResult, execute_step

_logger = get_logger("runtime.plan_execute")

_DEFAULT_MAX_REPLANS = 2
_DEFAULT_MAX_CONCURRENCY = 4


@dataclass
class CompletedStep:
    """A step that has finished successfully, carried into replans / synthesis."""

    id: str
    output: dict[str, Any] | None


@dataclass
class PlanContext:
    """Input to the planner: the goal, prior successful steps, and (on a corrective
    retry) the validation error to fix."""

    goal: str
    completed: list[CompletedStep] = field(default_factory=list)
    error: str | None = None


@dataclass
class ExecutedStep:
    """One executed step's outcome (for tracing / synthesis)."""

    id: str
    status: str  # "succeeded" | "failed" | "skipped"
    output: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class PlanExecuteResult:
    """The result of a plan-execute turn: final reply plus what happened."""

    text: str
    steps: list[ExecutedStep]
    replans: int


# A planner turns a PlanContext into a raw workflow-shaped plan dict.
Planner = Callable[[PlanContext], Awaitable[dict[str, Any]]]
# A synthesizer turns the goal + completed steps into a user-facing final reply.
Synthesizer = Callable[[str, list[CompletedStep]], Awaitable[str]]
# A step runner executes one step; defaults to workflow.steps.execute_step.
StepRunner = Callable[[Any, dict[str, Any], StepContext], Awaitable[StepResult]]


async def _plan_with_retry(
    planner: Planner,
    *,
    goal: str,
    completed: list[CompletedStep],
    error: str | None = None,
) -> WorkflowDef | None:
    """Call the planner and validate its plan; on a validation error, retry ONCE with
    the error fed back. Returns the validated ``WorkflowDef`` or ``None`` if both the
    initial plan and the corrective retry fail validation (fail-closed)."""
    raw = await planner(PlanContext(goal=goal, completed=list(completed), error=error))
    validation_error: str
    try:
        return parse_definition(raw)
    except WorkflowDefinitionError as exc:
        validation_error = str(exc)
        _logger.warn("plan_invalid_retrying", error=validation_error)
    retry = await planner(PlanContext(goal=goal, completed=list(completed), error=validation_error))
    try:
        return parse_definition(retry)
    except WorkflowDefinitionError as exc2:
        _logger.warn("plan_invalid_after_retry", error=exc2)
        return None


async def _execute_plan(
    wf: WorkflowDef,
    ctx: StepContext,
    step_runner: StepRunner,
    *,
    inputs: dict[str, Any],
    step_outputs: dict[str, Any],
    max_concurrency: int,
) -> tuple[list[ExecutedStep], bool]:
    """Drive the plan wave-by-wave using the workflow layer's pure DAG functions.

    ``step_outputs`` accumulates ``{step_id: {"output": ...}}`` (seeded from prior
    replans) so later steps resolve ``${steps.x.output}`` against earlier ones.
    Returns the executed steps this pass and whether any step failed (which the
    caller uses to decide whether to replan). Stops the wave loop on the first
    failure so the caller can replan the remainder rather than cascade-skipping it.
    """
    statuses = {s.id: ("succeeded" if s.id in step_outputs else "pending") for s in wf.steps}
    sem = asyncio.Semaphore(max(1, max_concurrency))
    executed: list[ExecutedStep] = []

    async def _one(step_id: str) -> tuple[str, StepResult]:
        context = {"inputs": inputs, "steps": step_outputs}
        async with sem:
            return step_id, await step_runner(wf.step(step_id), context, ctx)

    while True:
        skips = compute_cascade_skips(wf, statuses)
        if skips:
            for sid in skips:
                statuses[sid] = "skipped"
                executed.append(ExecutedStep(id=sid, status="skipped"))
            continue
        ready = compute_ready(wf, statuses)
        if not ready:
            return executed, False
        results = await asyncio.gather(*(_one(sid) for sid in ready))
        failed = False
        for sid, res in results:
            statuses[sid] = res.status
            executed.append(
                ExecutedStep(id=sid, status=res.status, output=res.output, error=res.error)
            )
            if res.status == "succeeded":
                step_outputs[sid] = {"output": res.output}
            else:
                failed = True
        if failed:
            return executed, True


async def run_plan_execute(
    goal: str,
    *,
    planner: Planner | None = None,
    synthesizer: Synthesizer | None = None,
    step_runner: StepRunner | None = None,
    agent_name: str | None = None,
    principal: Any = None,
    inputs: dict[str, Any] | None = None,
    max_replans: int = _DEFAULT_MAX_REPLANS,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
) -> PlanExecuteResult:
    """Run one plan-and-execute turn: plan → execute → (replan)* → synthesize.

    Every collaborator is injectable; production defaults bind the real LLM planner /
    synthesizer and ``execute_step``. Returns a ``PlanExecuteResult`` even when planning
    or a step fails — a degraded final reply is synthesized from whatever completed.
    """
    planner = planner or _default_planner
    synthesizer = synthesizer or _default_synthesizer
    runner = step_runner or execute_step
    ctx = StepContext(
        run_id=f"pe-{uuid.uuid4().hex[:12]}", agent_name=agent_name, principal=principal
    )
    seed_inputs = dict(inputs or {})

    step_outputs: dict[str, Any] = {}
    all_executed: list[ExecutedStep] = []
    replans = 0

    while True:
        completed = [CompletedStep(id=sid, output=v["output"]) for sid, v in step_outputs.items()]
        wf = await _plan_with_retry(planner, goal=goal, completed=completed)
        if wf is None:
            _logger.warn("plan_execute_no_valid_plan", replans=replans)
            break
        executed, failed = await _execute_plan(
            wf,
            ctx,
            runner,
            inputs=seed_inputs,
            step_outputs=step_outputs,
            max_concurrency=max_concurrency,
        )
        all_executed.extend(executed)
        if not failed or replans >= max_replans:
            break
        replans += 1
        _logger.info("plan_execute_replanning", attempt=replans)

    completed = [CompletedStep(id=sid, output=v["output"]) for sid, v in step_outputs.items()]
    text = await synthesizer(goal, completed)
    return PlanExecuteResult(text=text, steps=all_executed, replans=replans)


# ── default (production) collaborators ─────────────────────────────────────────

_PLANNER_SYSTEM = (
    "You are a planner. Decompose the user's goal into a minimal ordered plan of steps "
    "as JSON matching this shape: "
    '{"name": "plan", "steps": [{"id": "s1", "type": "agent", "prompt": "..."}, '
    '{"id": "s2", "type": "agent", "prompt": "... ${steps.s1.output.text} ...", '
    '"depends_on": ["s1"]}]}. '
    "Each step is an 'agent' step whose prompt fully specifies one subtask. Reference a "
    "prior step's result with ${steps.<id>.output.text}. Declare depends_on for ordering. "
    "Keep it acyclic and minimal. Reply with JSON only, no prose."
)


async def _default_planner(pc: PlanContext) -> dict[str, Any]:
    """Production planner: one LLM call returning a workflow-shaped plan dict.

    Follows the codebase's one-off structured-call pattern (temperature=0, manual JSON
    parse with fence handling). Lazy imports keep this off the module import path and
    break the loop<->plan_execute cycle.
    """
    from fleetent import agent_config
    from fleetent.model import ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
    cfg = policy.resolve("default")[0]
    if not cfg.model:
        return {}  # unresolved model → empty plan fails closed → corrective retry
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent")
    user = f"Goal:\n{pc.goal}"
    if pc.completed:
        done = "\n".join(f"- {c.id}: {c.output}" for c in pc.completed)
        user += f"\n\nAlready completed (plan only the REMAINING work):\n{done}"
    if pc.error:
        user += f"\n\nYour previous plan was invalid: {pc.error}\nReturn a corrected plan."
    resp = await client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": _PLANNER_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content or ""
    return _parse_plan_json(content)


def _parse_plan_json(content: str) -> dict[str, Any]:
    """Parse a plan dict from an LLM reply, stripping markdown fences. Returns an empty
    dict on failure (which fails parse_definition closed → corrective retry)."""
    import json

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _default_synthesizer(goal: str, completed: list[CompletedStep]) -> str:
    """Production synthesizer: one LLM call summarizing step outputs into a final reply.

    Degrades to a plain concatenation of step outputs if the LLM call fails, so the
    user always gets an answer.
    """
    joined = "\n\n".join(
        f"[{c.id}] {_text_of(c.output)}" for c in completed if c.output is not None
    )
    try:
        from openai import AsyncOpenAI

        from fleetent import agent_config
        from fleetent.model import ModelPolicySnapshot

        policy = ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
        cfg = policy.resolve("default")[0]
        if not cfg.model:
            return joined
        client = AsyncOpenAI(
            base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent"
        )
        resp = await client.chat.completions.create(
            model=cfg.model,
            messages=[
                {
                    "role": "system",
                    "content": "Synthesize the step results into one clear answer for the user.",
                },
                {"role": "user", "content": f"Goal: {goal}\n\nResults:\n{joined}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content or joined
    except Exception as exc:  # noqa: BLE001 — degrade to raw results; never fail the turn
        _logger.warn("plan_execute_synthesis_failed", exception=exc)
        return joined


def _text_of(output: dict[str, Any] | None) -> str:
    if not output:
        return ""
    if "text" in output:
        return str(output["text"])
    return str(output)
