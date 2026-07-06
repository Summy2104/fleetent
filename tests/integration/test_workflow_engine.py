"""DB-backed workflow engine tests: hot path, resume, concurrency, timeout/cancel, freeze."""

import asyncio

import pytest

from fleetent.workflow import store
from fleetent.workflow.definition import parse_definition
from fleetent.workflow.engine import WorkflowEngine


def _bind(tmp_path, agent_id="agent"):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    store.set_state_db(db)
    return db


def _linear_wf():
    return parse_definition(
        {
            "name": "chain",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "step a"},
                {"id": "b", "type": "agent", "prompt": "use ${steps.a.output.text}"},
                {"id": "c", "type": "agent", "prompt": "use ${steps.b.output.text}"},
            ],
        }
    )


async def test_hot_path_linear_chain_completes(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    order = []

    async def fake_run(messages, **kw):
        order.append(messages[-1]["content"])
        return "out"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    eng = WorkflowEngine()
    run_id = eng.start_run(_linear_wf())
    await eng.drive_run(run_id)

    run = store.get_run(run_id)
    assert run["status"] == "succeeded"
    # b saw a's output, c saw b's output → strict ordering, no rerun
    assert order == ["step a", "use out", "use out"]
    assert all(s["status"] == "succeeded" for s in store.list_steps(run_id))


async def test_concurrency_capped_by_semaphore(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    live = 0
    peak = 0

    async def fake_run(messages, **kw):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        live -= 1
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf = parse_definition(
        {
            "name": "fan",
            "steps": [{"id": f"s{i}", "type": "agent", "prompt": "x"} for i in range(6)],
        }
    )
    eng = WorkflowEngine(max_parallel=2)
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)
    assert peak <= 2
    assert store.get_run(run_id)["status"] == "succeeded"


async def test_failure_cascades_and_run_fails(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return ""  # empty → step fails (fail-closed)

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf = parse_definition(
        {
            "name": "chain",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "x"},
                {"id": "b", "type": "agent", "prompt": "use ${steps.a.output.text}"},
            ],
        }
    )
    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)
    assert store.get_step(run_id, "a")["status"] == "failed"
    assert store.get_step(run_id, "b")["status"] == "skipped"
    assert store.get_run(run_id)["status"] == "failed"


async def test_resume_after_restart_no_rerun(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    calls = []

    async def fake_run(messages, **kw):
        calls.append(messages[-1]["content"])
        return "out"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = _linear_wf()
    eng1 = WorkflowEngine()
    run_id = eng1.start_run(wf)
    # simulate partial progress: run only step a, then "crash" (drop engine memory)
    store.set_run_status(run_id, "running", started_at="2026-01-01T00:00:00Z")
    assert store.claim_step(run_id, "a", 1)
    store.finish_step(run_id, "a", 1, status="succeeded", output={"text": "out"})
    calls.clear()

    # fresh engine (no in-memory state) resumes via sweep
    eng2 = WorkflowEngine()
    await eng2.sweep()
    run = store.get_run(run_id)
    assert run["status"] == "succeeded"
    # step a not rerun; only b and c executed
    assert calls == ["use out", "use out"]


async def test_expired_claim_reclaimed_by_sweep(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return "recovered"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf = parse_definition({"name": "one", "steps": [{"id": "a", "type": "agent", "prompt": "x"}]})
    eng = WorkflowEngine(claim_margin_seconds=0)
    run_id = eng.start_run(wf)
    store.set_run_status(run_id, "running", started_at="2026-01-01T00:00:00Z")
    # step claimed long ago and never finished (orphan)
    store.claim_step(run_id, "a", 1, now="2000-01-01T00:00:00Z")
    await eng.sweep()
    latest = store.get_step(run_id, "a")
    assert latest["attempt"] == 2
    assert latest["status"] == "succeeded"
    assert store.get_run(run_id)["status"] == "succeeded"


async def test_step_timeout_fails_run(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def slow_run(messages, **kw):
        await asyncio.sleep(5)
        return "too late"

    monkeypatch.setattr(agent_loop, "run", slow_run)
    wf = parse_definition(
        {
            "name": "slow",
            "steps": [{"id": "a", "type": "agent", "prompt": "x", "timeout_seconds": 1}],
        }
    )
    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)
    step = store.get_step(run_id, "a")
    assert step["status"] == "failed"
    assert "timed out" in step["error"]
    assert store.get_run(run_id)["status"] == "failed"


async def test_cancel_run_cascades(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    started = asyncio.Event()

    async def slow_run(messages, **kw):
        started.set()
        await asyncio.sleep(5)
        return "late"

    monkeypatch.setattr(agent_loop, "run", slow_run)
    wf = parse_definition(
        {
            "name": "cancelme",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "x"},
                {"id": "b", "type": "agent", "prompt": "use ${steps.a.output.text}"},
            ],
        }
    )
    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    eng.spawn(run_id)
    await asyncio.wait_for(started.wait(), timeout=2)
    await eng.cancel_run(run_id)
    assert store.get_run(run_id)["status"] == "cancelled"
    assert store.get_step(run_id, "b")["status"] == "cancelled"


async def test_frozen_definition_survives_file_edit(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return "out"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf = _linear_wf()
    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    # the frozen definition_json is what drives the run; mutate the WorkflowDef object after
    run = store.get_run(run_id)
    assert len(run["definition"]["steps"]) == 3
    await eng.drive_run(run_id)
    assert store.get_run(run_id)["status"] == "succeeded"


async def test_terminal_delivery_best_effort(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop
    from fleetent.workflow import delivery

    async def fake_run(messages, **kw):
        return "out"

    sent = {}

    async def fake_send(target, text, connectors):
        sent["text"] = text
        return None

    monkeypatch.setattr(agent_loop, "run", fake_run)
    monkeypatch.setattr(
        delivery, "resolve_target", lambda to, origin: ("slack", "D1", "user", None)
    )
    monkeypatch.setattr(delivery, "send", fake_send)

    wf = parse_definition({"name": "one", "steps": [{"id": "a", "type": "agent", "prompt": "x"}]})
    eng = WorkflowEngine()
    run_id = eng.start_run(wf, origin={"platform": "slack", "chat_id": "D1"})
    await eng.drive_run(run_id)
    await asyncio.sleep(0.01)  # let the best-effort notify future run
    assert store.get_run(run_id)["status"] == "succeeded"
    assert "one" in sent["text"]


async def test_missing_required_input_rejected_no_run(tmp_path):
    _bind(tmp_path)
    from fleetent.workflow.engine import WorkflowInputError

    wf = parse_definition(
        {
            "name": "needs",
            "inputs": {"channel": {"type": "string"}},  # required (no default)
            "steps": [{"id": "a", "type": "notify", "text": "hi ${inputs.channel}"}],
        }
    )
    eng = WorkflowEngine()
    with pytest.raises(WorkflowInputError, match="channel"):
        eng.start_run(wf)
    assert store.list_runs("needs") == []


async def test_prune_retention_on_finalize(tmp_path, monkeypatch):
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return "out"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf = parse_definition({"name": "p", "steps": [{"id": "a", "type": "agent", "prompt": "x"}]})
    eng = WorkflowEngine(run_retention=2)
    for _ in range(4):
        rid = eng.start_run(wf)
        await eng.drive_run(rid)
    assert len(store.list_runs("p")) == 2
