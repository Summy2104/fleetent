"""Runnable demo of the deterministic multi-agent orchestration harness.

Shows the canonical "audit" shape end to end — fan-out across dimensions, a
per-item deep-dive pipeline, and adversarial majority-vote verification — with a
narrated, deterministic stub runner so it runs with no LLM/network. Pass
``--real`` to drive it through actual sub-agent runs against the demo agent.

    uv run python scripts/orchestration_demo.py            # stubbed, offline
    BENCH_E2E-style: --real needs FLEETENT_MODEL_PRIMARY_API_KEY + relay online

The point is to make the *orchestration control flow* visible: which sub-agents
fan out, how the pipeline stages chain per item, and how the verify stage votes.
"""

from __future__ import annotations

import argparse
import asyncio
import os

os.environ.setdefault("FLEETENT_HOME", os.path.abspath(".fleetent-dev"))
os.environ.setdefault("LOG_FORMAT", "console")


def _log(msg: str) -> None:
    print(msg, flush=True)


# --- Deterministic stub runner: canned, keyword-routed replies (no LLM) ---------

# Findings the "review" pipeline stage will surface per dimension.
_FINDINGS = {
    "correctness": "off-by-one in pagination offset",
    "security": "SQL built via f-string in search endpoint",
    "performance": "N+1 query in the KB retrieval loop",
}


async def _stub_runner(prompt: str) -> str:
    # Simulate real latency + interleaving so the concurrency narration is honest.
    await asyncio.sleep(0.05)
    low = prompt.lower()

    # verify stage: adversarial voter. Refute the one bogus finding, support real ones.
    if low.startswith("you are an adversarial verifier"):
        # The security finding is the "planted false positive" the panel should kill.
        if "sql built via f-string" in low:
            return "REFUTED: the f-string input is an int cast, not user-controlled."
        return "SUPPORTED: reproduced against the current code."

    # review stage: given a dimension, return that dimension's finding.
    for dim, finding in _FINDINGS.items():
        if dim in low:
            return finding

    return "no notable finding"


async def _demo(orch, *, verifiers: int) -> None:  # noqa: ANN001
    from fleetent.runtime.orchestration import OrchestrationResult

    dimensions = list(_FINDINGS)

    _log("=" * 68)
    _log("多 Agent 编排 harness demo — 代码审计场景")
    _log("=" * 68)

    # Phase 1: fan-out — one reviewer sub-agent per dimension, bounded concurrency.
    _log(f"\n[1] fan_out: 并发派 {len(dimensions)} 个维度审计子 agent (max_concurrency=2)")
    reviews = await orch.fan_out(
        [(d, f"Review the codebase for {d} issues.") for d in dimensions],
        max_concurrency=2,
    )
    for r in reviews:
        _log(f"    - {r.label:12} -> {r.output}")

    # Phase 2: pipeline — each finding flows through (normalize -> adversarial verify),
    # per-item, no barrier. The verify stage runs a majority-vote skeptic panel.
    _log(f"\n[2] pipeline: 逐条发现 normalize -> verify (每条 {verifiers} 票对抗校验)")

    async def _normalize(prev: OrchestrationResult, item, idx):  # noqa: ANN001
        return {"dimension": item.label, "finding": prev if isinstance(prev, str) else item.output}

    async def _verify_stage(prev, item, idx):  # noqa: ANN001
        claim = prev["finding"]
        verdict = await orch.verify(claim, voters=verifiers)
        tally = f"{sum(verdict.votes)}/{len(verdict.votes)} refute"
        status = "KILLED (false positive)" if verdict.refuted else "CONFIRMED"
        _log(f"    - [{prev['dimension']:12}] {claim!r}\n        votes={tally} -> {status}")
        return {**prev, "confirmed": verdict.survives}

    # Feed each review's output as the pipeline item (carry the label via a wrapper).
    items = [OrchestrationResult(label=r.label, output=r.output) for r in reviews if r.ok]
    verified = await orch.pipeline(items, _normalize, _verify_stage)

    # Phase 3: aggregate — deterministic fan-in of confirmed findings.
    confirmed = [v.output["finding"] for v in verified if v.ok and v.output["confirmed"]]
    _log("\n[3] aggregate: 汇总确认的发现")
    for f in confirmed:
        _log(f"    ✓ {f}")
    _log(f"\n结果: {len(confirmed)}/{len(items)} 条发现通过对抗校验 (1 条 security 误报被投票淘汰)")
    _log("=" * 68)


async def _main(args: argparse.Namespace) -> None:
    from fleetent.structured_logging import configure_structured_logging

    configure_structured_logging(console_level="error")
    from fleetent.runtime.orchestration import Orchestrator

    if args.real:
        orch = Orchestrator(default_max_concurrency=4)  # real sub-agent runner
        _log("MODE=real (真实子 agent 运行,需 relay + key)")
    else:
        orch = Orchestrator(runner=_stub_runner, default_max_concurrency=4)
        _log("MODE=stub (确定性桩,无需 LLM)")

    await _demo(orch, verifiers=args.verifiers)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--real", action="store_true", help="drive real sub-agent runs")
    ap.add_argument("--verifiers", type=int, default=3, help="adversarial voters per finding")
    main_args = ap.parse_args()
    asyncio.run(_main(main_args))


if __name__ == "__main__":
    main()
