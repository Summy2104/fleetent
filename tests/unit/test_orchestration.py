"""Unit tests for the deterministic multi-agent orchestration harness.

Pure unit: the sub-agent runner is injected as a stub, so no LLM/DB is touched.
Covers the four deterministic primitives — fan_out (bounded concurrency),
pipeline (per-item, no barrier), verify (adversarial majority vote, fail-closed),
and loop_until (deterministic accumulation).
"""

from __future__ import annotations

import asyncio

from fleetent.runtime.orchestration import Orchestrator, Verdict


def _echo_runner(text: str):
    async def _run(prompt: str) -> str:
        return f"echo:{prompt}"

    return _run


async def test_fan_out_runs_all_and_preserves_order() -> None:
    orch = Orchestrator(runner=_echo_runner(""))
    results = await orch.fan_out([("a", "p1"), ("b", "p2"), ("c", "p3")])
    assert [r.label for r in results] == ["a", "b", "c"]
    assert [r.output for r in results] == ["echo:p1", "echo:p2", "echo:p3"]
    assert all(r.ok for r in results)


async def test_fan_out_captures_failure_without_raising() -> None:
    async def _boom(prompt: str) -> str:
        if "bad" in prompt:
            raise RuntimeError("kaboom")
        return "ok"

    orch = Orchestrator(runner=_boom)
    results = await orch.fan_out([("good", "fine"), ("bad", "bad one")])
    assert results[0].ok and results[0].output == "ok"
    assert not results[1].ok and "kaboom" in (results[1].error or "")


async def test_fan_out_respects_max_concurrency() -> None:
    state = {"cur": 0, "peak": 0}

    async def _tracking(prompt: str) -> str:
        state["cur"] += 1
        state["peak"] = max(state["peak"], state["cur"])
        await asyncio.sleep(0.01)
        state["cur"] -= 1
        return "ok"

    orch = Orchestrator(runner=_tracking)
    tasks = [(f"t{i}", f"p{i}") for i in range(10)]
    await orch.fan_out(tasks, max_concurrency=3)
    assert state["peak"] <= 3


async def test_pipeline_flows_item_through_stages() -> None:
    orch = Orchestrator(runner=_echo_runner(""))

    async def s1(prev, item, idx):  # noqa: ANN001
        return prev + 1

    async def s2(prev, item, idx):  # noqa: ANN001
        return prev * 10

    results = await orch.pipeline([1, 2, 3], s1, s2)
    assert [r.output for r in results] == [20, 30, 40]


async def test_pipeline_stage_error_isolates_single_item() -> None:
    orch = Orchestrator(runner=_echo_runner(""))

    async def s1(prev, item, idx):  # noqa: ANN001
        if item == 2:
            raise ValueError("bad item")
        return prev

    results = await orch.pipeline([1, 2, 3], s1)
    assert results[0].ok and results[2].ok
    assert not results[1].ok and "bad item" in (results[1].error or "")


async def test_verify_majority_refute_marks_refuted() -> None:
    # Every voter refutes → claim is refuted, does not survive.
    async def _refuter(prompt: str) -> str:
        return "REFUTED: this is wrong"

    orch = Orchestrator(runner=_refuter)
    verdict = await orch.verify("the sky is green", voters=3)
    assert isinstance(verdict, Verdict)
    assert verdict.refuted is True
    assert verdict.survives is False


async def test_verify_majority_support_survives() -> None:
    async def _supporter(prompt: str) -> str:
        return "SUPPORTED: this holds up"

    orch = Orchestrator(runner=_supporter)
    verdict = await orch.verify("water is wet", voters=3)
    assert verdict.refuted is False
    assert verdict.survives is True


async def test_verify_failed_voter_defaults_to_refuted() -> None:
    # A voter that raises must count as "refuted" (fail-closed adversarial verify).
    calls = {"n": 0}

    async def _flaky(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "SUPPORTED"
        raise RuntimeError("voter crashed")

    orch = Orchestrator(runner=_flaky)
    verdict = await orch.verify("claim", voters=3)
    # 1 support + 2 crashed(=refuted) → majority refuted.
    assert verdict.refuted is True


async def test_loop_until_stops_on_done() -> None:
    orch = Orchestrator(runner=_echo_runner(""))
    rounds = {"n": 0}

    async def _produce(acc):  # noqa: ANN001
        rounds["n"] += 1
        return [rounds["n"]]

    def _done(acc):  # noqa: ANN001
        return len(acc) >= 3

    acc = await orch.loop_until(_produce, _done, max_rounds=10)
    assert acc == [1, 2, 3]
    assert rounds["n"] == 3


async def test_loop_until_caps_at_max_rounds() -> None:
    orch = Orchestrator(runner=_echo_runner(""))

    async def _produce(acc):  # noqa: ANN001
        return [1]

    def _never(acc):  # noqa: ANN001
        return False

    acc = await orch.loop_until(_produce, _never, max_rounds=4)
    assert len(acc) == 4
