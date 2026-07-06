"""Persistent workflow execution engine.

Eino's DAG readiness semantics (a step runs only when all control predecessors
have succeeded) driven off SQLite instead of memory, so a run survives process
restarts. Two drivers converge on the same idempotent claim: a hot path that
steps a run forward in-process the moment a step finishes (no poll latency), and
a cold sweep that resumes orphaned runs and reclaims expired claims after a
crash. Concurrency is capped by a semaphore; each step runs under a timeout
CancelToken chained to a run-level token for cooperative cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fleetent.runtime.cancellation import CancelToken
from fleetent.structured_logging import get_logger
from fleetent.workflow import delivery, store
from fleetent.workflow.definition import WorkflowDef, parse_definition
from fleetent.workflow.errors import WorkflowError
from fleetent.workflow.steps import StepContext, execute_step

logger = get_logger("workflow_engine")

DEFAULT_MAX_PARALLEL = 4
# Extra seconds beyond a step's own timeout before a still-"running" claim is deemed
# orphaned (crash) and reclaimed. Guards against reclaiming a step that is merely slow.
DEFAULT_CLAIM_MARGIN_SECONDS = 60
DEFAULT_SWEEP_INTERVAL_SECONDS = 30

_TERMINAL_STEP = frozenset({"succeeded", "failed", "skipped", "cancelled"})


class WorkflowInputError(WorkflowError):
    """Provided run inputs are missing a required parameter."""


# ── pure logic (no DB) ────────────────────────────────────────────────────────


def compute_ready(wf: WorkflowDef, statuses: dict[str, str]) -> list[str]:
    """Step ids whose every control predecessor has succeeded and are still pending."""
    ready = []
    for step in wf.steps:
        if statuses.get(step.id) != "pending":
            continue
        preds = wf.control_deps[step.id]
        if all(statuses.get(p) == "succeeded" for p in preds):
            ready.append(step.id)
    return ready


def compute_cascade_skips(wf: WorkflowDef, statuses: dict[str, str]) -> list[str]:
    """Pending steps that must be skipped because a control predecessor did not succeed.

    Iterated to a fixpoint by the caller: skipping one step can unblock skipping its
    dependents (a non-succeeded terminal predecessor propagates downstream).
    """
    skips = []
    for step in wf.steps:
        if statuses.get(step.id) != "pending":
            continue
        preds = wf.control_deps[step.id]
        if any(statuses.get(p) in ("failed", "skipped", "cancelled") for p in preds):
            skips.append(step.id)
    return skips


def compute_run_terminal_status(statuses: dict[str, str]) -> str | None:
    """The run's terminal status if all steps are terminal, else None.

    ``failed`` dominates (any failed step fails the run); otherwise ``cancelled`` if any
    step was cancelled; otherwise ``succeeded``.
    """
    if not statuses:
        return None
    if any(s not in _TERMINAL_STEP for s in statuses.values()):
        return None
    if any(s == "failed" for s in statuses.values()):
        return "failed"
    if any(s == "cancelled" for s in statuses.values()):
        return "cancelled"
    return "succeeded"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# ── engine ────────────────────────────────────────────────────────────────────


class WorkflowEngine:
    """Drives workflow runs to completion with hot-path stepping + a cold sweep."""

    def __init__(
        self,
        *,
        agent_name: str | None = None,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
        claim_margin_seconds: int = DEFAULT_CLAIM_MARGIN_SECONDS,
        sweep_interval_seconds: int = DEFAULT_SWEEP_INTERVAL_SECONDS,
        connectors_provider: Callable[[], dict[str, Any]] | None = None,
        run_retention: int = store._DEFAULT_RUN_RETENTION,
    ) -> None:
        self._agent_name = agent_name
        self._sem = asyncio.Semaphore(max_parallel)
        self._claim_margin = claim_margin_seconds
        self._sweep_interval = sweep_interval_seconds
        self._connectors_provider = connectors_provider or (lambda: {})
        self._run_retention = run_retention
        self._run_tokens: dict[str, CancelToken] = {}
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._sweep_task: asyncio.Task[None] | None = None

    # -- run start / drive ------------------------------------------------------

    def start_run(
        self,
        wf: WorkflowDef,
        *,
        inputs: dict[str, Any] | None = None,
        principal: dict[str, Any] | None = None,
        origin: dict[str, Any] | None = None,
        deliver: dict[str, Any] | None = None,
    ) -> str:
        """Validate inputs, freeze the definition + principal, and create the run row.

        Does not begin execution — call :meth:`drive_run` (tests) or :meth:`spawn`
        (background). Raises ``WorkflowInputError`` before any row is written when a
        required input is missing.
        """
        merged = self._merge_inputs(wf, inputs or {})
        run_id = f"wfr-{uuid.uuid4().hex[:12]}"
        store.create_run(
            run_id=run_id,
            workflow_name=wf.name,
            definition=_definition_to_dict(wf),
            inputs=merged,
            principal=principal,
            origin=origin,
            deliver=deliver,
            step_ids=[s.id for s in wf.steps],
        )
        return run_id

    def _merge_inputs(self, wf: WorkflowDef, provided: dict[str, Any]) -> dict[str, Any]:
        merged = dict(provided)
        for name, spec in wf.inputs.items():
            if name in merged:
                continue
            if spec.required:
                raise WorkflowInputError(f"missing required input {name!r}")
            merged[name] = spec.default
        return merged

    def spawn(self, run_id: str) -> asyncio.Task[None]:
        """Drive a run in a background task (the non-blocking trigger path)."""
        task = asyncio.create_task(self.drive_run(run_id))
        self._run_tasks[run_id] = task
        task.add_done_callback(lambda t: self._run_tasks.pop(run_id, None))
        return task

    async def drive_run(self, run_id: str) -> None:
        """Advance a run wave-by-wave until every step is terminal (or it blocks)."""
        run = store.get_run(run_id)
        if run is None or run["status"] in store.RUN_TERMINAL:
            return
        wf = parse_definition(run["definition"])  # frozen snapshot, not the on-disk file
        token = self._run_tokens.setdefault(run_id, CancelToken())
        if run["status"] == "pending":
            store.set_run_status(run_id, "running", started_at=_now())

        while True:
            if token.is_cancelled():
                break
            statuses = self._statuses(run_id)
            # Cascade-skip to a fixpoint before computing readiness.
            skipped = compute_cascade_skips(wf, statuses)
            if skipped:
                for sid in skipped:
                    store.skip_step(run_id, sid)
                continue
            ready = compute_ready(wf, statuses)
            if not ready:
                break
            await asyncio.gather(*(self._run_step(run_id, wf, sid) for sid in ready))

        self._finalize(run_id, wf, run)

    def _statuses(self, run_id: str) -> dict[str, str]:
        return {s["step_id"]: s["status"] for s in store.list_steps(run_id)}

    async def _run_step(self, run_id: str, wf: WorkflowDef, step_id: str) -> None:
        step = wf.step(step_id)
        latest = store.get_step(run_id, step_id)
        if latest is None:
            return
        attempt = latest["attempt"]
        if not store.claim_step(run_id, step_id, attempt):
            return  # lost the claim to a concurrent driver

        run = store.get_run(run_id)
        assert run is not None
        token = self._run_tokens.setdefault(run_id, CancelToken())
        step_token = CancelToken(deadline=time.monotonic() + step.timeout_seconds, parent=token)
        ctx = StepContext(
            run_id=run_id,
            agent_name=self._agent_name,
            principal=self._principal_obj(run.get("principal")),
            origin=run.get("origin"),
            cancel_token=step_token,
            outbound_connectors=self._connectors_provider(),
        )
        context = self._build_context(run_id, run.get("inputs") or {})

        async with self._sem:
            try:
                result = await asyncio.wait_for(
                    execute_step(step, context, ctx), timeout=step.timeout_seconds
                )
            except TimeoutError:
                from fleetent.workflow.steps import StepResult

                result = StepResult("failed", error=f"step timed out after {step.timeout_seconds}s")
            except asyncio.CancelledError:
                store.finish_step(
                    run_id, step_id, attempt, status="cancelled", error="run cancelled"
                )
                raise

        if result.status == "failed" and attempt <= step.max_attempts:
            store.finish_step(run_id, step_id, attempt, status="failed", error=result.error)
            store.open_retry_attempt(run_id, step_id, attempt)  # next wave picks up the retry
            return
        store.finish_step(
            run_id,
            step_id,
            attempt,
            status=result.status,
            output=result.output,
            error=result.error,
        )

    def _build_context(self, run_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        steps_ctx: dict[str, Any] = {}
        for s in store.list_steps(run_id):
            if s["status"] == "succeeded":
                steps_ctx[s["step_id"]] = {"output": s.get("output")}
        return {"inputs": inputs, "steps": steps_ctx}

    def _finalize(self, run_id: str, wf: WorkflowDef, run: dict[str, Any]) -> None:
        statuses = self._statuses(run_id)
        terminal = compute_run_terminal_status(statuses)
        if terminal is None:
            return  # still blocked (e.g. cancelled mid-flight); sweep will revisit
        current = store.get_run(run_id)
        if current is None or current["status"] in store.RUN_TERMINAL:
            return
        error = self._collect_error(run_id, statuses) if terminal == "failed" else None
        store.set_run_status(run_id, terminal, error=error, ended_at=_now())
        self._run_tokens.pop(run_id, None)
        # Best-effort terminal notification + retention (never change the terminal outcome).
        asyncio.ensure_future(self._notify_terminal(run_id, wf, terminal, error))
        try:
            store.prune_runs(wf.name, retention=self._run_retention)
        except Exception as exc:  # noqa: BLE001 — retention is a side channel
            logger.warn("workflow_prune_failed", run=run_id, error=exc)

    def _collect_error(self, run_id: str, statuses: dict[str, str]) -> str:
        for sid, st in statuses.items():
            if st == "failed":
                row = store.get_step(run_id, sid)
                return f"step {sid!r} failed: {(row or {}).get('error')}"
        return "run failed"

    async def _notify_terminal(
        self, run_id: str, wf: WorkflowDef, terminal: str, error: str | None
    ) -> None:
        run = store.get_run(run_id)
        if run is None:
            return
        target = delivery.resolve_target(run.get("deliver"), run.get("origin"))
        if target is None:
            logger.info("workflow_terminal_no_target", run=run_id, status=terminal)
            return
        text = f"workflow {wf.name!r} {terminal}"
        if error:
            text += f": {error}"
        try:
            err = await delivery.send(target, text, self._connectors_provider())
            if err:
                logger.warn("workflow_terminal_delivery_failed", run=run_id, error=err)
        except Exception as exc:  # noqa: BLE001 — terminal delivery is best-effort
            logger.warn("workflow_terminal_delivery_raised", run=run_id, error=exc)

    @staticmethod
    def _principal_obj(principal: dict[str, Any] | None) -> Any:
        if principal is None:
            return None
        from fleetent.identity import Principal

        try:
            return Principal(**principal)
        except Exception:  # noqa: BLE001 — a stored shape we can't reconstruct: pass the dict
            return principal

    # -- cancellation -----------------------------------------------------------

    async def cancel_run(self, run_id: str) -> None:
        """Cancel a run: signal its token, cancel the drive task, mark open steps cancelled."""
        token = self._run_tokens.setdefault(run_id, CancelToken())
        token.cancel()
        task = self._run_tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            # Bulkheaded teardown: a cancelled/erroring drive task must not crash cancel_run.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        store.cancel_open_steps(run_id)
        current = store.get_run(run_id)
        if current is not None and current["status"] not in store.RUN_TERMINAL:
            store.set_run_status(run_id, "cancelled", ended_at=_now())
        self._run_tokens.pop(run_id, None)

    # -- cold sweep -------------------------------------------------------------

    async def sweep(self) -> None:
        """One recovery pass: reclaim expired claims and drive every active run forward."""
        for run in store.list_active_runs():
            run_id = run["id"]
            try:
                wf = parse_definition(run["definition"])
            except Exception as exc:  # noqa: BLE001 — a corrupt frozen def must not wedge sweep
                logger.warn("workflow_sweep_bad_def", run=run_id, error=exc)
                continue
            self._reclaim_expired(run_id, wf)
            await self.drive_run(run_id)

    def _reclaim_expired(self, run_id: str, wf: WorkflowDef) -> None:
        now = datetime.now(UTC)
        for s in store.list_steps(run_id):
            if s["status"] != "running" or not s.get("claimed_at"):
                continue
            step = wf.step(s["step_id"])
            window = step.timeout_seconds + self._claim_margin
            try:
                claimed = _parse_ts(s["claimed_at"])
            except ValueError:
                continue
            if (now - claimed).total_seconds() > window:
                store.reclaim_expired_step(run_id, s["step_id"], s["attempt"])

    async def start(self) -> None:
        """Start the periodic cold-sweep owner task (managed lifespan)."""
        if self._sweep_task is not None:
            return
        self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a sweep error must not kill the loop
                logger.warn("workflow_sweep_error", error=exc)
            await asyncio.sleep(self._sweep_interval)

    async def stop(self) -> None:
        """Stop the sweep task; bulkheaded so teardown never crashes the process."""
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            # Bulkheaded: teardown never crashes the process (owner-task contract).
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._sweep_task
            self._sweep_task = None


def _definition_to_dict(wf: WorkflowDef) -> dict[str, Any]:
    """Serialize a WorkflowDef back to the raw mapping shape parse_definition accepts."""
    steps: list[dict[str, Any]] = []
    for s in wf.steps:
        row: dict[str, Any] = {"id": s.id, "type": s.type}
        if s.depends_on:
            row["depends_on"] = list(s.depends_on)
        if s.timeout_seconds != 300:
            row["timeout_seconds"] = s.timeout_seconds
        if s.max_attempts:
            row["retry"] = {"max_attempts": s.max_attempts}
        if s.type == "tool":
            row["tool"] = s.tool
            row["args"] = s.args
        elif s.type == "agent":
            if s.agent is not None:
                row["agent"] = s.agent
            row["prompt"] = s.prompt
            if s.output_schema is not None:
                row["output_schema"] = s.output_schema
        else:
            row["text"] = s.text
            if s.to is not None:
                row["to"] = s.to
        steps.append(row)
    out: dict[str, Any] = {"name": wf.name, "description": wf.description, "steps": steps}
    if wf.inputs:
        out["inputs"] = {
            n: {"type": i.type, **({"default": i.default} if not i.required else {})}
            for n, i in wf.inputs.items()
        }
    return out
