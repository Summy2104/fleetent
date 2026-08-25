"""Deterministic multi-agent orchestration harness (agent-side).

Composes the sub-agent fan-out primitive into *code-driven* orchestration
patterns — bounded fan-out, per-item pipeline, adversarial verify, and
loop-until. Control flow here is deterministic (loops/conditionals in code),
distinct from the model-driven ReAct loop each sub-agent runs internally: the
orchestrator decides the shape (what fans out, what verifies, what repeats), the
sub-agents decide their own steps.

Design contracts:
- Agent-side only. MUST NOT import ``fleetent.platform.*``.
- Injectable ``runner`` (no global singleton): tests pass a stub; production
  lazily binds the real sub-agent runner (``loop.run(is_sub_agent=True)``).
- Bounded concurrency via a semaphore — closes the unbounded-``gather`` gap in
  the raw ``SubAgentExecutor``.
- Best-effort adversarial verify: a verifier that raises counts as *refuted*
  (fail-closed), so a crashed skeptic never lets a false claim survive.
- Owner-task cancellation is inherited from the sub-agent runner it wraps; the
  orchestrator adds no long-lived resources of its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.orchestration")

# A runner takes a prompt and returns the sub-agent's final text reply.
Runner = Callable[[str], Awaitable[str]]

# A pipeline stage: (prev_result, original_item, index) -> next_result.
Stage = Callable[[Any, Any, int], Awaitable[Any]]

_DEFAULT_MAX_CONCURRENCY = 8
_DEFAULT_VOTERS = 3


@dataclass
class OrchestrationResult:
    """One orchestrated unit of work: its label, output, and any captured error."""

    label: str
    output: Any
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class Verdict:
    """Adversarial verification outcome for a single claim."""

    claim: str
    refuted: bool
    votes: list[bool] = field(default_factory=list)  # per-voter: did it refute?

    @property
    def survives(self) -> bool:
        return not self.refuted


def _normalize_tasks(tasks: Sequence[Any]) -> list[tuple[str, str]]:
    """Accept ``[(label, prompt), ...]`` or ``[prompt, ...]`` → ``[(label, prompt)]``."""
    norm: list[tuple[str, str]] = []
    for i, t in enumerate(tasks):
        if isinstance(t, tuple):
            label, prompt = t
            norm.append((str(label), str(prompt)))
        else:
            norm.append((f"task-{i}", str(t)))
    return norm


_VERIFY_INSTRUCTION = (
    "You are an adversarial verifier. Try to REFUTE the following claim. "
    "Reply starting with 'REFUTED' if it is wrong, unsupported, or you are "
    "uncertain; reply starting with 'SUPPORTED' only if it clearly holds. "
    "Default to REFUTED when in doubt.\n\nClaim: "
)


def _build_verify_prompts(claim: str, voters: int, lenses: Sequence[str] | None) -> list[str]:
    """One prompt per voter. When lenses are given, each voter gets a distinct lens
    (perspective-diverse verify); otherwise all voters share the base instruction."""
    if lenses:
        return [
            f"{_VERIFY_INSTRUCTION}{claim}\n\nJudge specifically through the "
            f"'{lenses[i % len(lenses)]}' lens."
            for i in range(voters)
        ]
    return [f"{_VERIFY_INSTRUCTION}{claim}"] * voters


def _parse_refuted(reply: str) -> bool:
    """Map a verifier reply to refuted?/not. Fail-closed: anything not clearly
    SUPPORTED counts as refuted."""
    return not reply.strip().upper().startswith("SUPPORTED")


async def _default_runner(prompt: str) -> str:
    """Production runner: one sub-agent ReAct run. Lazy import breaks the
    loop<->orchestration<->sub_agent import cycle."""
    from fleetent.runtime import loop as agent_loop

    return await agent_loop.run(
        messages=[{"role": "user", "content": prompt}],
        is_sub_agent=True,
    )


class Orchestrator:
    """Code-driven coordinator over sub-agent runs."""

    def __init__(
        self,
        runner: Runner | None = None,
        *,
        default_max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._runner = runner or _default_runner
        self._default_max_concurrency = max(1, default_max_concurrency)

    async def _run(self, prompt: str) -> str:
        return await self._runner(prompt)

    async def fan_out(
        self,
        tasks: Sequence[Any],
        *,
        max_concurrency: int | None = None,
    ) -> list[OrchestrationResult]:
        """Run tasks concurrently under a concurrency cap; failures are captured,
        never raised. Result order matches input order."""
        norm = _normalize_tasks(tasks)
        sem = asyncio.Semaphore(max_concurrency or self._default_max_concurrency)

        async def _one(label: str, prompt: str) -> OrchestrationResult:
            async with sem:
                try:
                    out = await self._run(prompt)
                    return OrchestrationResult(label=label, output=out)
                except Exception as exc:  # noqa: BLE001 — capture per-task, never abort batch
                    _logger.warn("orchestration_fan_out_task_failed", label=label, error=exc)
                    return OrchestrationResult(label=label, output=None, error=str(exc))

        return list(await asyncio.gather(*(_one(lbl, p) for lbl, p in norm)))

    async def pipeline(
        self,
        items: Sequence[Any],
        *stages: Stage,
        max_concurrency: int | None = None,
    ) -> list[OrchestrationResult]:
        """Flow each item through all stages independently (no barrier between
        stages). A stage that raises drops only its item to an error result."""
        sem = asyncio.Semaphore(max_concurrency or self._default_max_concurrency)

        async def _chain(idx: int, item: Any) -> OrchestrationResult:
            async with sem:
                cur = item
                try:
                    for stage in stages:
                        cur = await stage(cur, item, idx)
                    return OrchestrationResult(label=f"item-{idx}", output=cur)
                except Exception as exc:  # noqa: BLE001 — isolate one item's failure
                    _logger.warn("orchestration_pipeline_item_failed", index=idx, error=exc)
                    return OrchestrationResult(label=f"item-{idx}", output=None, error=str(exc))

        return list(await asyncio.gather(*(_chain(i, it) for i, it in enumerate(items))))

    async def verify(
        self,
        claim: str,
        *,
        voters: int = _DEFAULT_VOTERS,
        lenses: Sequence[str] | None = None,
        threshold: int | None = None,
    ) -> Verdict:
        """Adversarial majority vote: spawn ``voters`` skeptic runs, each prompted
        to refute. A crashed voter counts as refuted (fail-closed). The claim is
        marked refuted when refuting votes reach ``threshold`` (default: majority)."""
        voters = max(1, voters)
        prompts = _build_verify_prompts(claim, voters, lenses)

        async def _vote(prompt: str) -> bool:
            try:
                return _parse_refuted(await self._run(prompt))
            except Exception as exc:  # noqa: BLE001 — a dead skeptic fails closed
                _logger.warn("orchestration_verify_voter_failed", error=exc)
                return True

        votes = list(await asyncio.gather(*(_vote(p) for p in prompts)))
        thr = threshold if threshold is not None else (len(votes) // 2 + 1)
        refuted_count = sum(1 for v in votes if v)
        return Verdict(claim=claim, refuted=refuted_count >= thr, votes=votes)

    async def loop_until(
        self,
        produce: Callable[[list[Any]], Awaitable[list[Any]]],
        done: Callable[[list[Any]], bool],
        *,
        max_rounds: int = 5,
    ) -> list[Any]:
        """Deterministically accumulate: call ``produce(acc)`` each round, extend
        the accumulator, stop when ``done(acc)`` or ``max_rounds`` is reached."""
        acc: list[Any] = []
        for _ in range(max(1, max_rounds)):
            batch = await produce(acc)
            acc.extend(batch)
            if done(acc):
                break
        return acc
