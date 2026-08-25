"""Complex workflow scenarios: diamond DAG, mixed-type chains, partial failure
with concurrent success branches, retry success, multi-run isolation, deep
nested mapping, and fan-out/fan-in topologies.

All tests use the DB-backed engine with monkeypatched executors.
"""

import asyncio
import json

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


def _stub_tool_registry(monkeypatch):
    """Stub the tool registry so parse_definition accepts tool steps."""
    from fleetent.tools import registry

    _schemas = {
        "web_fetch": {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        "get_current_time": {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        "calculate": {
            "type": "function",
            "function": {
                "name": "calculate",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        },
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: _schemas.get(name))
    monkeypatch.setattr(registry, "is_registered", lambda name: name in _schemas)


# ── diamond DAG: A → B, A → C, B+C → D ─────────────────────────────────────


async def test_diamond_dag_all_paths_converge(tmp_path, monkeypatch):
    """D only runs after both B and C have succeeded; A's output flows through both."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    order = []

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        order.append(content)
        if "step a" in content:
            return json.dumps({"val": 10})
        if "branch b" in content:
            return json.dumps({"doubled": 20})
        if "branch c" in content:
            return json.dumps({"tripled": 30})
        return json.dumps({"sum": 50})

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "diamond",
            "steps": [
                {
                    "id": "a",
                    "type": "agent",
                    "prompt": "step a",
                    "output_schema": {"type": "object", "required": ["val"]},
                },
                {
                    "id": "b",
                    "type": "agent",
                    "prompt": "branch b from ${steps.a.output.val}",
                    "output_schema": {"type": "object", "required": ["doubled"]},
                },
                {
                    "id": "c",
                    "type": "agent",
                    "prompt": "branch c from ${steps.a.output.val}",
                    "output_schema": {"type": "object", "required": ["tripled"]},
                },
                {
                    "id": "d",
                    "type": "agent",
                    "prompt": "merge ${steps.b.output.doubled} and ${steps.c.output.tripled}",
                    "depends_on": ["b", "c"],
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    run = store.get_run(run_id)
    assert run["status"] == "succeeded"
    assert all(s["status"] == "succeeded" for s in store.list_steps(run_id))
    assert order[0] == "step a"
    assert "merge 20 and 30" in order[-1]


# ── mixed type chain: tool → agent → notify ─────────────────────────────────


async def test_mixed_type_chain_tool_agent_notify(tmp_path, monkeypatch):
    """tool output flows into agent prompt, agent output flows into notify text."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop
    from fleetent.tools import registry
    from fleetent.workflow import delivery

    _stub_tool_registry(monkeypatch)
    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "none")
    monkeypatch.setattr(registry, "dispatch", lambda *a, **k: '{"fetched": "hello world"}')

    async def fake_run(messages, **kw):
        return json.dumps({"summary": "summarized: hello world"})

    monkeypatch.setattr(agent_loop, "run", fake_run)

    sent = {}

    async def fake_send(target, text, connectors):
        sent["text"] = text
        return None

    monkeypatch.setattr(
        delivery, "resolve_target", lambda to, origin: ("slack", "C1", "channel", None)
    )
    monkeypatch.setattr(delivery, "send", fake_send)

    wf = parse_definition(
        {
            "name": "mixed-chain",
            "steps": [
                {"id": "fetch", "type": "tool", "tool": "web_fetch", "args": {}},
                {
                    "id": "analyze",
                    "type": "agent",
                    "prompt": "analyze: ${steps.fetch.output.fetched}",
                    "output_schema": {
                        "type": "object",
                        "required": ["summary"],
                        "properties": {"summary": {"type": "string"}},
                    },
                },
                {
                    "id": "report",
                    "type": "notify",
                    "text": "Report: ${steps.analyze.output.summary}",
                    "to": {"platform": "slack", "target": "C1"},
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf, origin={"platform": "slack", "chat_id": "C1"})
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    assert sent["text"] == "Report: summarized: hello world"


# ── partial failure: one branch fails, other succeeds, join skipped ──────────


async def test_partial_failure_one_branch_fails_join_skipped(tmp_path, monkeypatch):
    """In a diamond, if C fails, D is skipped; B still succeeds. Run is 'failed'."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        if "fail me" in content:
            return ""  # empty → fail-closed
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "partial-fail",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "start"},
                {"id": "b", "type": "agent", "prompt": "branch b ok"},
                {"id": "c", "type": "agent", "prompt": "fail me"},
                {
                    "id": "d",
                    "type": "agent",
                    "prompt": "join ${steps.b.output.text} ${steps.c.output.text}",
                    "depends_on": ["b", "c"],
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    statuses = {s["step_id"]: s["status"] for s in store.list_steps(run_id)}
    assert statuses["a"] == "succeeded"
    assert statuses["b"] == "succeeded"
    assert statuses["c"] == "failed"
    assert statuses["d"] == "skipped"
    assert store.get_run(run_id)["status"] == "failed"


# ── retry success: step fails once, retry succeeds ──────────────────────────


async def test_retry_step_succeeds_on_second_attempt(tmp_path, monkeypatch):
    """A step with max_attempts=1 fails the first time, retries, and succeeds."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    flaky_calls = {"n": 0}

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        if "do something" in content:
            flaky_calls["n"] += 1
            if flaky_calls["n"] == 1:
                return ""  # fail-closed: empty reply on first attempt
        return "recovered"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "retry-wf",
            "steps": [
                {
                    "id": "flaky",
                    "type": "agent",
                    "prompt": "do something",
                    "retry": {"max_attempts": 1},
                },
                {"id": "after", "type": "agent", "prompt": "use ${steps.flaky.output.text}"},
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    assert flaky_calls["n"] == 2  # first attempt failed, second succeeded
    step = store.get_step(run_id, "flaky")
    assert step["attempt"] == 2
    assert step["status"] == "succeeded"


# ── retry exhausted: step fails all attempts ────────────────────────────────


async def test_retry_exhausted_fails_run(tmp_path, monkeypatch):
    """A step with max_attempts=1 that fails both times fails the run."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return ""  # always fail-closed

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "retry-exhaust",
            "steps": [
                {
                    "id": "always_fail",
                    "type": "agent",
                    "prompt": "do something",
                    "retry": {"max_attempts": 1},
                },
                {
                    "id": "after",
                    "type": "agent",
                    "prompt": "use ${steps.always_fail.output.text}",
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "failed"
    statuses = {s["step_id"]: s["status"] for s in store.list_steps(run_id)}
    assert statuses["always_fail"] == "failed"
    assert statuses["after"] == "skipped"


# ── multi-run isolation: concurrent runs of the same workflow ────────────────


async def test_concurrent_runs_isolated(tmp_path, monkeypatch):
    """Two runs of the same workflow execute independently; no cross-contamination."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        await asyncio.sleep(0.01)
        return f"reply-to-{content}"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "parallel-runs",
            "inputs": {"tag": {"type": "string"}},
            "steps": [
                {"id": "work", "type": "agent", "prompt": "${inputs.tag}"},
            ],
        }
    )

    eng = WorkflowEngine()
    run_a = eng.start_run(wf, inputs={"tag": "alpha"})
    run_b = eng.start_run(wf, inputs={"tag": "beta"})
    await asyncio.gather(eng.drive_run(run_a), eng.drive_run(run_b))

    assert store.get_run(run_a)["status"] == "succeeded"
    assert store.get_run(run_b)["status"] == "succeeded"
    step_a = store.get_step(run_a, "work")
    step_b = store.get_step(run_b, "work")
    assert step_a["output"]["text"] == "reply-to-alpha"
    assert step_b["output"]["text"] == "reply-to-beta"


# ── deep nested output mapping ──────────────────────────────────────────────


async def test_deep_nested_output_mapping(tmp_path, monkeypatch):
    """Step B references deeply nested fields from step A's structured output."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        if "extract" in content:
            return json.dumps(
                {
                    "contract": {
                        "parties": [
                            {"name": "Acme", "role": "buyer"},
                            {"name": "Beta", "role": "seller"},
                        ],
                        "amount": 50000,
                    }
                }
            )
        # second step: verify prompt contains resolved nested fields
        return f"verified: {content}"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "nested-map",
            "steps": [
                {
                    "id": "extract",
                    "type": "agent",
                    "prompt": "extract contract data",
                    "output_schema": {
                        "type": "object",
                        "required": ["contract"],
                    },
                },
                {
                    "id": "verify",
                    "type": "agent",
                    "prompt": (
                        "verify buyer=${steps.extract.output.contract.parties.0.name} "
                        "amount=${steps.extract.output.contract.amount}"
                    ),
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    step_v = store.get_step(run_id, "verify")
    assert "Acme" in step_v["output"]["text"]
    assert "50000" in step_v["output"]["text"]


# ── fan-out/fan-in: 1 → N → 1 ──────────────────────────────────────────────


async def test_fan_out_fan_in_topology(tmp_path, monkeypatch):
    """One root step fans out to 3 parallel branches, all converge to a final merge."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    execution_order = []

    async def fake_run(messages, **kw):
        content = messages[-1]["content"]
        execution_order.append(content.split()[0])  # first word as tag
        await asyncio.sleep(0.01)
        if "root" in content:
            return json.dumps({"data": "base"})
        if "worker" in content:
            return json.dumps({"result": f"done-{content.split()[-1]}"})
        # merge
        return "all merged"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "fan-out-in",
            "steps": [
                {
                    "id": "root",
                    "type": "agent",
                    "prompt": "root init",
                    "output_schema": {"type": "object", "required": ["data"]},
                },
                {
                    "id": "w1",
                    "type": "agent",
                    "prompt": "worker 1",
                    "output_schema": {"type": "object", "required": ["result"]},
                },
                {
                    "id": "w2",
                    "type": "agent",
                    "prompt": "worker 2",
                    "output_schema": {"type": "object", "required": ["result"]},
                },
                {
                    "id": "w3",
                    "type": "agent",
                    "prompt": "worker 3",
                    "output_schema": {"type": "object", "required": ["result"]},
                },
                {
                    "id": "merge",
                    "type": "agent",
                    "prompt": (
                        "merge ${steps.w1.output.result} ${steps.w2.output.result} "
                        "${steps.w3.output.result}"
                    ),
                    "depends_on": ["w1", "w2", "w3"],
                },
            ],
        }
    )

    eng = WorkflowEngine(max_parallel=4)
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    # root ran first, merge ran last
    assert execution_order[0] == "root"
    assert execution_order[-1] == "merge"
    merge_step = store.get_step(run_id, "merge")
    assert merge_step["output"]["text"] == "all merged"


# ── multi-layer DAG: A→B→D, A→C→E, D+E→F ──────────────────────────────────


async def test_multi_layer_dag(tmp_path, monkeypatch):
    """Two independent chains merge at a final step; tests deep DAG readiness."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    order = []

    async def fake_run(messages, **kw):
        tag = messages[-1]["content"]
        order.append(tag)
        return json.dumps({"v": tag})

    monkeypatch.setattr(agent_loop, "run", fake_run)

    _schema = {"type": "object", "required": ["v"]}
    wf = parse_definition(
        {
            "name": "multi-layer",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "a", "output_schema": _schema},
                {
                    "id": "b",
                    "type": "agent",
                    "prompt": "b",
                    "depends_on": ["a"],
                    "output_schema": _schema,
                },
                {
                    "id": "c",
                    "type": "agent",
                    "prompt": "c",
                    "depends_on": ["a"],
                    "output_schema": _schema,
                },
                {
                    "id": "d",
                    "type": "agent",
                    "prompt": "d",
                    "depends_on": ["b"],
                    "output_schema": _schema,
                },
                {
                    "id": "e",
                    "type": "agent",
                    "prompt": "e",
                    "depends_on": ["c"],
                    "output_schema": _schema,
                },
                {
                    "id": "f",
                    "type": "agent",
                    "prompt": "f: ${steps.d.output.v} ${steps.e.output.v}",
                    "depends_on": ["d", "e"],
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    assert order[0] == "a"
    assert order[-1] == "f: d e"
    assert all(s["status"] == "succeeded" for s in store.list_steps(run_id))


# ── inputs with defaults and overrides ──────────────────────────────────────


async def test_inputs_default_and_override(tmp_path, monkeypatch):
    """Required inputs must be provided; optional inputs use defaults when omitted."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    captured_prompt = {}

    async def fake_run(messages, **kw):
        captured_prompt["content"] = messages[-1]["content"]
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "input-test",
            "inputs": {
                "channel": {"type": "string"},  # required
                "mode": {"type": "string", "default": "auto"},  # optional
            },
            "steps": [
                {
                    "id": "work",
                    "type": "agent",
                    "prompt": "ch=${inputs.channel} mode=${inputs.mode}",
                },
            ],
        }
    )

    eng = WorkflowEngine()
    # provide required, rely on default for mode
    run_id = eng.start_run(wf, inputs={"channel": "#general"})
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    assert captured_prompt["content"] == "ch=#general mode=auto"


async def test_inputs_override_default(tmp_path, monkeypatch):
    """When an optional input is explicitly provided, the override takes precedence."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    captured_prompt = {}

    async def fake_run(messages, **kw):
        captured_prompt["content"] = messages[-1]["content"]
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "input-override",
            "inputs": {
                "channel": {"type": "string"},
                "mode": {"type": "string", "default": "auto"},
            },
            "steps": [
                {
                    "id": "work",
                    "type": "agent",
                    "prompt": "ch=${inputs.channel} mode=${inputs.mode}",
                },
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf, inputs={"channel": "#dev", "mode": "manual"})
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    assert captured_prompt["content"] == "ch=#dev mode=manual"


# ── cascade skip propagates through multiple layers ─────────────────────────


async def test_cascade_skip_multi_layer(tmp_path, monkeypatch):
    """A failure at the root cascades skips through all downstream layers."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return ""  # fail-closed

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "cascade-deep",
            "steps": [
                {"id": "root", "type": "agent", "prompt": "x"},
                {"id": "mid", "type": "agent", "prompt": "${steps.root.output.text}"},
                {"id": "leaf", "type": "agent", "prompt": "${steps.mid.output.text}"},
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    statuses = {s["step_id"]: s["status"] for s in store.list_steps(run_id)}
    assert statuses["root"] == "failed"
    assert statuses["mid"] == "skipped"
    assert statuses["leaf"] == "skipped"
    assert store.get_run(run_id)["status"] == "failed"


# ── tool step with async dispatch ────────────────────────────────────────────


async def test_tool_step_async_dispatch(tmp_path, monkeypatch):
    """Tool dispatch returns an awaitable; engine awaits it correctly."""
    _bind(tmp_path)
    from fleetent.tools import registry

    _stub_tool_registry(monkeypatch)

    async def async_dispatch(name, args, **kw):
        await asyncio.sleep(0.01)
        return json.dumps({"time": "2026-07-07T00:00:00Z"})

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "none")
    monkeypatch.setattr(registry, "dispatch", async_dispatch)

    wf = parse_definition(
        {
            "name": "async-tool",
            "steps": [
                {"id": "t", "type": "tool", "tool": "get_current_time", "args": {}},
            ],
        }
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(wf)
    await eng.drive_run(run_id)

    assert store.get_run(run_id)["status"] == "succeeded"
    step = store.get_step(run_id, "t")
    assert step["output"]["time"] == "2026-07-07T00:00:00Z"


# ── cancel mid-run with fan-out: running steps cancelled, pending skipped ───


async def test_cancel_during_fan_out(tmp_path, monkeypatch):
    """Cancelling a run with multiple in-flight steps cancels all open steps."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    started = asyncio.Event()

    async def slow_run(messages, **kw):
        started.set()
        await asyncio.sleep(10)
        return "late"

    monkeypatch.setattr(agent_loop, "run", slow_run)

    wf = parse_definition(
        {
            "name": "cancel-fan",
            "steps": [
                {"id": "s1", "type": "agent", "prompt": "x"},
                {"id": "s2", "type": "agent", "prompt": "x"},
                {
                    "id": "join",
                    "type": "agent",
                    "prompt": "merge",
                    "depends_on": ["s1", "s2"],
                },
            ],
        }
    )

    eng = WorkflowEngine(max_parallel=4)
    run_id = eng.start_run(wf)
    eng.spawn(run_id)
    await asyncio.wait_for(started.wait(), timeout=2)
    await eng.cancel_run(run_id)

    assert store.get_run(run_id)["status"] == "cancelled"
    statuses = {s["step_id"]: s["status"] for s in store.list_steps(run_id)}
    assert statuses["join"] == "cancelled"


# ── sweep recovers a run left in "running" state ────────────────────────────


async def test_sweep_recovers_stalled_run(tmp_path, monkeypatch):
    """A run left in 'running' with no engine is recovered by sweep."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return "swept"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {
            "name": "stalled",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "x"},
                {"id": "b", "type": "agent", "prompt": "use ${steps.a.output.text}"},
            ],
        }
    )

    eng1 = WorkflowEngine()
    run_id = eng1.start_run(wf)
    # simulate partial: a succeeded, b still pending, run is "running"
    store.set_run_status(run_id, "running", started_at="2026-01-01T00:00:00Z")
    store.claim_step(run_id, "a", 1)
    store.finish_step(run_id, "a", 1, status="succeeded", output={"text": "done"})

    # fresh engine sweeps and finishes the run
    eng2 = WorkflowEngine()
    await eng2.sweep()

    assert store.get_run(run_id)["status"] == "succeeded"
    assert store.get_step(run_id, "b")["status"] == "succeeded"


# ── principal and origin are frozen in the run ───────────────────────────────


async def test_principal_and_origin_frozen(tmp_path, monkeypatch):
    """Principal and origin provided at start_run are persisted and available to steps."""
    _bind(tmp_path)
    from fleetent.runtime import loop as agent_loop

    seen_kw = {}

    async def fake_run(messages, **kw):
        seen_kw.update(kw)
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    wf = parse_definition(
        {"name": "frozen", "steps": [{"id": "a", "type": "agent", "prompt": "x"}]}
    )

    eng = WorkflowEngine()
    run_id = eng.start_run(
        wf,
        principal={"user_id": "u1", "tenant_id": "t1"},
        origin={"platform": "slack", "chat_id": "D123"},
    )
    await eng.drive_run(run_id)

    run = store.get_run(run_id)
    assert run["principal"] == {"user_id": "u1", "tenant_id": "t1"}
    assert run["origin"]["platform"] == "slack"
