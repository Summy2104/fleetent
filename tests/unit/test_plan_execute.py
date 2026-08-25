"""Plan-and-Execute control strategy (agent-side, injectable, no real LLM/DB).

Covers the switchable ``control_strategy`` config projection and the plan → execute
→ replan → synthesis controller built on top of the reused workflow layer (pure DAG
functions + step executor + definition validation). All tests stub the planner and
the step runner; nothing here touches a real model endpoint or database.
"""

from __future__ import annotations

from dataclasses import fields

import pytest
import yaml

from fleetent import agent_config


def _agent_doc(name: str = "a", **overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
    }
    doc.update(overrides)
    return doc


def _write_agent(root, name: str, **overrides: object):
    doc = _agent_doc(name=name, **overrides)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return d


# ── Task 1: control_strategy config projection ─────────────────────────────


def test_control_strategy_defaults_to_react() -> None:
    af = agent_config.AgentFile.model_validate(_agent_doc(name="bare"))
    assert af.control_strategy == "react"


def test_control_strategy_parses_plan_execute() -> None:
    af = agent_config.AgentFile.model_validate(
        _agent_doc(name="p", control_strategy="plan_execute")
    )
    assert af.control_strategy == "plan_execute"


def test_control_strategy_rejects_unknown_value() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(_agent_doc(control_strategy="chain_of_thought"))


def test_governance_default_control_strategy_is_react() -> None:
    from fleetent.runtime.snapshot import GovernanceConfig

    assert GovernanceConfig().control_strategy == "react"


def test_control_strategy_projects_into_governance(tmp_path) -> None:
    from fleetent.runtime.snapshot import _governance_from_file

    _write_agent(tmp_path, "p", control_strategy="plan_execute")
    agent = agent_config.load_agent_file(tmp_path / "p")
    governance = _governance_from_file(agent)
    assert governance.control_strategy == "plan_execute"


def test_governance_has_control_strategy_field() -> None:
    from fleetent.runtime.snapshot import GovernanceConfig

    names = {f.name for f in fields(GovernanceConfig)}
    assert "control_strategy" in names


# ── Task 2: planner → validated WorkflowDef (+ one corrective retry) ────────


def _valid_plan() -> dict[str, object]:
    return {
        "name": "plan",
        "steps": [
            {"id": "a", "type": "agent", "prompt": "do a"},
            {
                "id": "b",
                "type": "agent",
                "prompt": "use ${steps.a.output.text}",
                "depends_on": ["a"],
            },
        ],
    }


def _cyclic_plan() -> dict[str, object]:
    return {
        "name": "plan",
        "steps": [
            {"id": "a", "type": "agent", "prompt": "x", "depends_on": ["b"]},
            {"id": "b", "type": "agent", "prompt": "y", "depends_on": ["a"]},
        ],
    }


async def test_planner_valid_plan_parses() -> None:
    from fleetent.runtime import plan_execute

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        return _valid_plan()

    wf = await plan_execute._plan_with_retry(_planner, goal="g", completed=[])
    assert wf is not None
    assert [s.id for s in wf.steps] == ["a", "b"]


async def test_planner_invalid_plan_triggers_one_corrective_retry() -> None:
    from fleetent.runtime import plan_execute

    calls: list[str | None] = []

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        calls.append(pc.error)
        # First call returns a cyclic (invalid) plan; the corrective retry (error set) fixes it.
        return _valid_plan() if pc.error is not None else _cyclic_plan()

    wf = await plan_execute._plan_with_retry(_planner, goal="g", completed=[])
    assert wf is not None
    assert [s.id for s in wf.steps] == ["a", "b"]
    # Exactly two calls: initial + one corrective retry carrying the validation error.
    assert len(calls) == 2
    assert calls[0] is None
    assert calls[1] is not None  # corrective retry got the error hint


async def test_planner_invalid_twice_returns_none() -> None:
    from fleetent.runtime import plan_execute

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        return _cyclic_plan()  # never valid

    wf = await plan_execute._plan_with_retry(_planner, goal="g", completed=[])
    assert wf is None


# ── Task 3: execute reuses the workflow DAG + threads step outputs ──────────


def _echo_runner(record: list[str] | None = None):
    """A step runner that echoes the rendered prompt as the step's text output.

    Because execute threads ``${steps.x.output.text}`` through the real workflow
    ``render`` context, a downstream step's rendered prompt proves the upstream
    output reached it.
    """
    from fleetent.workflow.steps import StepResult

    async def _run(step, context, ctx):  # noqa: ANN001
        if record is not None:
            record.append(step.id)
        # step.prompt was already validated; render happens inside the real executor,
        # but since we bypass it, resolve the one ${steps..} ref ourselves for the test.
        from fleetent.workflow.mapping import render

        rendered = render(step.prompt, context)
        return StepResult("succeeded", output={"text": f"ran:{rendered}"})

    return _run


async def test_execute_runs_in_dependency_order_and_threads_output() -> None:
    from fleetent.runtime import plan_execute
    from fleetent.workflow.definition import parse_definition
    from fleetent.workflow.steps import StepContext

    wf = parse_definition(_valid_plan())
    order: list[str] = []
    ctx = StepContext(run_id="t")
    step_outputs: dict[str, object] = {}
    executed, failed = await plan_execute._execute_plan(
        wf,
        ctx,
        _echo_runner(order),
        inputs={},
        step_outputs=step_outputs,
        max_concurrency=4,
    )
    assert failed is False
    assert order == ["a", "b"]  # b depends on a
    # b's prompt referenced ${steps.a.output.text}; that must have resolved to a's output.
    b_out = step_outputs["b"]["output"]["text"]
    assert "ran:do a" in b_out  # a's output text "ran:do a" flowed into b


async def test_execute_reports_failure_for_replan() -> None:
    from fleetent.runtime import plan_execute
    from fleetent.workflow.definition import parse_definition
    from fleetent.workflow.steps import StepContext, StepResult

    async def _failing_runner(step, context, ctx):  # noqa: ANN001
        if step.id == "a":
            return StepResult("failed", error="boom")
        return StepResult("succeeded", output={"text": "ok"})

    wf = parse_definition(_valid_plan())
    executed, failed = await plan_execute._execute_plan(
        wf,
        StepContext(run_id="t"),
        _failing_runner,
        inputs={},
        step_outputs={},
        max_concurrency=4,
    )
    assert failed is True
    # b depends on failed a → it is cascade-skipped, never run.
    statuses = {e.id: e.status for e in executed}
    assert statuses["a"] == "failed"
    assert statuses.get("b") in (None, "skipped")


# ── Task 4: replan on step failure, bounded by max_replans ─────────────────


async def test_replan_triggered_on_failure_then_succeeds() -> None:
    from fleetent.runtime import plan_execute
    from fleetent.workflow.steps import StepResult

    plan_calls: list[list[str]] = []

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        plan_calls.append([c.id for c in pc.completed])
        return {"name": "p", "steps": [{"id": "s", "type": "agent", "prompt": "go"}]}

    # Fail the very first step execution, succeed thereafter → exactly one replan.
    calls = {"n": 0}

    async def _runner(step, context, ctx):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return StepResult("failed", error="transient")
        return StepResult("succeeded", output={"text": "done"})

    result = await plan_execute.run_plan_execute(
        "goal",
        planner=_planner,
        synthesizer=_join_synth,
        step_runner=_runner,
        max_replans=2,
    )
    assert result.replans == 1
    assert "done" in result.text


async def test_replan_capped_at_max_replans() -> None:
    from fleetent.runtime import plan_execute
    from fleetent.workflow.steps import StepResult

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        return {"name": "p", "steps": [{"id": "s", "type": "agent", "prompt": "go"}]}

    async def _always_fail(step, context, ctx):  # noqa: ANN001
        return StepResult("failed", error="permanent")

    result = await plan_execute.run_plan_execute(
        "goal",
        planner=_planner,
        synthesizer=_join_synth,
        step_runner=_always_fail,
        max_replans=2,
    )
    # 1 initial attempt + 2 replans = capped; replans counter stops at max.
    assert result.replans == 2


# ── Task 5: synthesis + PlanExecuteResult ──────────────────────────────────


async def _join_synth(goal: str, completed) -> str:  # noqa: ANN001
    return " | ".join(f"{c.id}={_out_text(c.output)}" for c in completed)


def _out_text(output) -> str:  # noqa: ANN001
    return "" if not output else str(output.get("text", output))


async def test_synthesis_receives_completed_and_result_shape() -> None:
    from fleetent.runtime import plan_execute
    from fleetent.workflow.steps import StepResult

    async def _planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        return _valid_plan()

    async def _runner(step, context, ctx):  # noqa: ANN001
        return StepResult("succeeded", output={"text": f"out-{step.id}"})

    seen: dict[str, object] = {}

    async def _synth(goal: str, completed) -> str:  # noqa: ANN001
        seen["goal"] = goal
        seen["ids"] = [c.id for c in completed]
        return "FINAL"

    result = await plan_execute.run_plan_execute(
        "my goal", planner=_planner, synthesizer=_synth, step_runner=_runner
    )
    assert isinstance(result, plan_execute.PlanExecuteResult)
    assert result.text == "FINAL"
    assert result.replans == 0
    assert seen["goal"] == "my goal"
    assert set(seen["ids"]) == {"a", "b"}
    assert {e.id for e in result.steps} == {"a", "b"}


async def test_no_valid_plan_still_synthesizes_degraded_reply() -> None:
    from fleetent.runtime import plan_execute

    async def _bad_planner(pc: plan_execute.PlanContext) -> dict[str, object]:
        return _cyclic_plan()  # never valid, even on retry

    result = await plan_execute.run_plan_execute(
        "goal", planner=_bad_planner, synthesizer=_join_synth, step_runner=_echo_runner()
    )
    # No steps executed, but the turn still returns a (empty) synthesized reply.
    assert result.steps == []
    assert result.replans == 0
    assert isinstance(result.text, str)


# ── Task 6: loop.run() dispatches on strategy; is_sub_agent forces ReAct ────


async def test_loop_run_dispatches_to_plan_execute(monkeypatch) -> None:
    from fleetent.runtime import loop, plan_execute
    from fleetent.runtime.snapshot import GovernanceConfig

    seen: dict[str, object] = {}

    async def _fake_pe(goal, **kwargs):  # noqa: ANN001, ANN003
        seen["goal"] = goal
        seen["agent_name"] = kwargs.get("agent_name")
        return plan_execute.PlanExecuteResult(text="PE-REPLY", steps=[], replans=0)

    async def _fake_inner(*a, **k):  # noqa: ANN002, ANN003
        seen["inner"] = True
        return "REACT-REPLY"

    monkeypatch.setattr(plan_execute, "run_plan_execute", _fake_pe)
    monkeypatch.setattr(loop, "_run_inner", _fake_inner)

    reply = await loop.run(
        messages=[{"role": "user", "content": "achieve X"}],
        agent_name="demo",
        governance=GovernanceConfig(control_strategy="plan_execute"),
    )
    assert reply == "PE-REPLY"
    assert seen["goal"] == "achieve X"
    assert seen["agent_name"] == "demo"
    assert "inner" not in seen  # ReAct loop was NOT used


async def test_loop_run_sub_agent_forces_react(monkeypatch) -> None:
    from fleetent.runtime import loop, plan_execute
    from fleetent.runtime.snapshot import GovernanceConfig

    seen: dict[str, object] = {}

    async def _fake_pe(goal, **kwargs):  # noqa: ANN001, ANN003
        seen["pe"] = True
        return plan_execute.PlanExecuteResult(text="PE", steps=[], replans=0)

    async def _fake_inner(*a, **k):  # noqa: ANN002, ANN003
        return "REACT-REPLY"

    monkeypatch.setattr(plan_execute, "run_plan_execute", _fake_pe)
    monkeypatch.setattr(loop, "_run_inner", _fake_inner)

    # Even with plan_execute configured, a sub-agent run must use ReAct (no recursion).
    reply = await loop.run(
        messages=[{"role": "user", "content": "subtask"}],
        is_sub_agent=True,
        governance=GovernanceConfig(control_strategy="plan_execute"),
    )
    assert reply == "REACT-REPLY"
    assert "pe" not in seen


async def test_loop_run_react_default_unaffected(monkeypatch) -> None:
    from fleetent.runtime import loop
    from fleetent.runtime.snapshot import GovernanceConfig

    async def _fake_inner(*a, **k):  # noqa: ANN002, ANN003
        return "REACT-REPLY"

    monkeypatch.setattr(loop, "_run_inner", _fake_inner)

    reply = await loop.run(
        messages=[{"role": "user", "content": "hi"}],
        governance=GovernanceConfig(),  # default control_strategy="react"
    )
    assert reply == "REACT-REPLY"
