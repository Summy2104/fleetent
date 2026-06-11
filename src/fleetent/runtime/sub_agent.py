"""Sub-agent executor: run multiple tasks in parallel via asyncio.gather."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fleetent.identity import Principal
from fleetent.runtime import sub_agent_lifecycle
from fleetent.runtime.cancellation import CancelToken
from fleetent.runtime.sub_agent_lifecycle import SubAgentLifecycle, SubAgentState
from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.sub_agent")


@dataclass
class SubAgentResult:
    name: str
    result: Any
    error: str | None
    parent_session_id: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SubAgentExecutor:
    async def run(
        self,
        tasks: list[dict[str, str]],
        parent_principal: Principal | None,
        parent_agent_id: int | None,
        parent_session_id: str,
        *,
        timeout_seconds: int | None = None,
        cancel_token: CancelToken | None = None,
    ) -> list[SubAgentResult]:
        # sub_agent_runs schema is created by the unified AGENT_STATE_MIGRATIONS at boot;
        # no per-call table init (the table lives in the per-agent agent_state.db).
        effective_timeout = sub_agent_lifecycle.resolve_timeout(timeout_seconds)
        batch_token = cancel_token if cancel_token is not None else CancelToken()
        coros = [
            self._run_one(
                task,
                parent_principal,
                parent_agent_id,
                parent_session_id,
                effective_timeout,
                batch_token,
            )
            for task in tasks
        ]
        return list(await asyncio.gather(*coros))

    async def _run_one(
        self,
        task: dict[str, str],
        parent_principal: Principal | None,
        parent_agent_id: int | None,
        parent_session_id: str,
        timeout_seconds: int,
        batch_token: CancelToken,
    ) -> SubAgentResult:
        name = task["name"]
        prompt = task["prompt"]
        lc = SubAgentLifecycle(
            run_id=uuid.uuid4().hex,
            parent_session_id=parent_session_id,
            name=name,
            timeout_seconds=timeout_seconds,
            created_at=_now_iso(),
        )

        # External cancel may already have fired before this task starts: persist
        # pending → cancelled without ever entering running (started_at stays None).
        # On the normal path `pending` is transient (microseconds, no await before
        # running), so the first persisted row is `running` — one fewer fsync on
        # the hot path while keeping every observable terminal state intact.
        if batch_token.is_cancelled():
            sub_agent_lifecycle.upsert(lc)
            self._transition(lc, SubAgentState.cancelled)
            return SubAgentResult(
                name=name, result=None, error=None, parent_session_id=parent_session_id
            )

        # Per-task token: own deadline OR parent/external cancel (D3 parent link).
        child = CancelToken(deadline=time.monotonic() + timeout_seconds, parent=batch_token)
        lc.started_at = _now_iso()
        self._transition(lc, SubAgentState.running)

        # Lazy import breaks the loop <-> sub_agent cycle: loop imports
        # SubAgentExecutor at module level, so sub_agent must not import loop at
        # top level (import-order-dependent crash otherwise).
        from fleetent.runtime import loop as agent_loop

        try:
            result = await agent_loop.run(
                messages=[{"role": "user", "content": prompt}],
                principal=parent_principal,
                is_sub_agent=True,
                cancel_token=child,
            )
        except Exception as exc:
            _logger.warn("sub_agent_task_failed", task=name, error=str(exc))
            self._transition(lc, SubAgentState.failed, error=str(exc))
            return SubAgentResult(
                name=name, result=None, error=str(exc), parent_session_id=parent_session_id
            )

        if child.is_cancelled():
            # Distinguish own-deadline (timed_out) from external/parent cancel.
            passed = child.deadline is not None and time.monotonic() >= child.deadline
            self._transition(lc, SubAgentState.timed_out if passed else SubAgentState.cancelled)
            return SubAgentResult(
                name=name, result=result, error=None, parent_session_id=parent_session_id
            )

        self._transition(lc, SubAgentState.succeeded)
        return SubAgentResult(
            name=name, result=result, error=None, parent_session_id=parent_session_id
        )

    def _transition(
        self, lc: SubAgentLifecycle, dst: SubAgentState, *, error: str | None = None
    ) -> None:
        sub_agent_lifecycle.validate_transition(lc.state, dst)
        lc.state = dst
        if error is not None:
            lc.error = error
        if dst is not SubAgentState.running:
            lc.ended_at = _now_iso()
        sub_agent_lifecycle.upsert(lc)
