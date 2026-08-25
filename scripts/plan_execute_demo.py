"""Runnable demo of the Plan-and-Execute control strategy.

Shows the full turn shape — plan → execute (dependency-ordered) → replan on a
failed step → synthesize — with a narrated, deterministic stub planner + step
runner so it runs with no LLM/network. The point is to make the *control flow*
visible: what the planner emits, how steps thread outputs, and how one failed
step triggers a bounded replan rather than aborting the turn.

    uv run python scripts/plan_execute_demo.py

Contrast with ReAct (the default strategy): there the model decides the next step
after each observation; here the whole plan is produced up front, executed as a
DAG, and only *re-planned* when a step fails.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("FLEETENT_HOME", os.path.abspath(".fleetent-dev"))
os.environ.setdefault("LOG_FORMAT", "console")


def _log(msg: str) -> None:
    print(msg, flush=True)


# --- Deterministic stub planner: emits a 3-step research plan (a → b, a → c) ----


def _plan_for(goal: str) -> dict[str, object]:
    return {
        "name": "research_plan",
        "description": f"plan for: {goal}",
        "steps": [
            {"id": "gather", "type": "agent", "prompt": f"Gather sources on: {goal}"},
            {
                "id": "analyze",
                "type": "agent",
                "prompt": "Analyze ${steps.gather.output.text}",
                "depends_on": ["gather"],
            },
            {
                "id": "risks",
                "type": "agent",
                "prompt": "List risks from ${steps.gather.output.text}",
                "depends_on": ["gather"],
            },
        ],
    }


def _replan_remaining(goal: str) -> dict[str, object]:
    # After the first attempt failed on "analyze", the planner (seeing gather done)
    # regenerates just the remaining work with a more robust prompt.
    return {
        "name": "research_plan_v2",
        "description": "replan after analyze failed",
        "steps": [
            {
                "id": "analyze",
                "type": "agent",
                "prompt": "Carefully analyze the gathered sources (retry)",
            },
            {
                "id": "risks",
                "type": "agent",
                "prompt": "List risks (retry)",
                "depends_on": ["analyze"],
            },
        ],
    }


async def _main() -> None:
    from fleetent.structured_logging import configure_structured_logging

    configure_structured_logging(console_level="error")

    from fleetent.runtime import plan_execute
    from fleetent.workflow.mapping import render
    from fleetent.workflow.steps import StepResult

    goal = "the impact of on-prem LLM deployment on data sovereignty"

    _log("=" * 70)
    _log("Plan-and-Execute demo — 研究任务")
    _log("=" * 70)
    _log(f"\nGoal: {goal}")

    plan_calls = {"n": 0}

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        plan_calls["n"] += 1
        if pc.completed:
            done = ", ".join(c.id for c in pc.completed)
            _log(f"\n[replan #{plan_calls['n'] - 1}] planner 已知完成: [{done}] → 重规划剩余步骤")
            return _replan_remaining(goal)
        _log("\n[plan] planner 把目标分解为 3 步 (gather → analyze, gather → risks)")
        _log("[execute] 按 depends_on 波次执行，${steps.x.output} 串联数据")
        return _plan_for(goal)

    # Fail "analyze" exactly once (first execution) so the replan path is exercised.
    fail_once = {"analyze": True}

    async def _runner(step, context, ctx):  # noqa: ANN001
        rendered = render(step.prompt, context)
        if step.id == "analyze" and fail_once.get("analyze"):
            fail_once["analyze"] = False
            _log(f"    ✗ [{step.id:8}] 执行失败 (模拟瞬时错误)")
            return StepResult("failed", error="transient analyze error")
        _log(f"    ✓ [{step.id:8}] {rendered[:52]}")
        return StepResult("succeeded", output={"text": f"result-of-{step.id}"})

    async def _synth(g: str, completed) -> str:  # noqa: ANN001
        ids = ", ".join(c.id for c in completed)
        return f"综合 [{ids}] 的结果，回答了「{g}」。"

    result = await plan_execute.run_plan_execute(
        goal,
        planner=_planner,
        synthesizer=_synth,
        step_runner=_runner,
        max_replans=2,
    )

    _log("\n[synthesize] 汇总所有成功步骤为最终回复")
    _log(f"\n最终回复: {result.text}")
    _log(
        f"\n结果: replan 次数={result.replans}, "
        f"执行步骤={len([s for s in result.steps if s.status == 'succeeded'])} 成功 / "
        f"{len([s for s in result.steps if s.status == 'failed'])} 失败 / "
        f"{len([s for s in result.steps if s.status == 'skipped'])} 跳过"
    )
    _log("=" * 70)


if __name__ == "__main__":
    asyncio.run(_main())
