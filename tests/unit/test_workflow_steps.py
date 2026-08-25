"""Unit tests for workflow step executors (tool / agent / notify).

LLM and dispatch are mocked; no DB. Verifies rendering, output coercion,
governance fail-closed, structured output, and delivery.
"""

from fleetent.workflow.definition import StepDef
from fleetent.workflow.steps import StepContext, execute_step


def _step(**over):
    base = dict(id="s", type="tool", depends_on=(), timeout_seconds=300, max_attempts=0)
    base.update(over)
    return StepDef(**base)


def _ctx(**over):
    base = dict(run_id="wfr-1", agent_name="host")
    base.update(over)
    return StepContext(**base)


_CONTEXT = {"inputs": {"channel": "#x"}, "steps": {"up": {"output": {"body": "hello", "n": 2}}}}


# ── tool step ─────────────────────────────────────────────────────────────────


async def test_tool_direct_dispatch_and_json_output(monkeypatch):
    from fleetent.tools import registry

    captured = {}

    def fake_dispatch(name, args, **kw):
        captured["name"], captured["args"] = name, args
        return '{"count": 3}'

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "low")
    monkeypatch.setattr(registry, "dispatch", fake_dispatch)

    step = _step(tool="counter", args={"text": "${steps.up.output.body}"})
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "succeeded"
    assert res.output == {"count": 3}
    assert captured["args"] == {"text": "hello"}  # rendered


async def test_tool_non_json_output_wrapped(monkeypatch):
    from fleetent.tools import registry

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "none")
    monkeypatch.setattr(registry, "dispatch", lambda *a, **k: "plain text")
    res = await execute_step(_step(tool="t", args={}), _CONTEXT, _ctx())
    assert res.output == {"text": "plain text"}


async def test_tool_high_risk_fails_closed(monkeypatch):
    from fleetent.tools import registry

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "high")
    called = {"dispatched": False}
    monkeypatch.setattr(
        registry, "dispatch", lambda *a, **k: called.__setitem__("dispatched", True)
    )
    res = await execute_step(_step(tool="danger", args={}), _CONTEXT, _ctx())
    assert res.status == "failed"
    assert "approval" in res.error
    assert called["dispatched"] is False


async def test_tool_critical_rejected(monkeypatch):
    from fleetent.tools import registry

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "critical")
    monkeypatch.setattr(registry, "dispatch", lambda *a, **k: "nope")
    res = await execute_step(_step(tool="rm", args={}), _CONTEXT, _ctx())
    assert res.status == "failed"


async def test_tool_dispatch_exception_fails(monkeypatch):
    from fleetent.tools import registry

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "low")
    monkeypatch.setattr(registry, "dispatch", boom)
    res = await execute_step(_step(tool="t", args={}), _CONTEXT, _ctx())
    assert res.status == "failed"
    assert "kaboom" in res.error


async def test_tool_mapping_failure_fails_closed(monkeypatch):
    from fleetent.tools import registry

    monkeypatch.setattr(registry, "evaluate_risk_level", lambda *a, **k: "low")
    monkeypatch.setattr(registry, "dispatch", lambda *a, **k: "ok")
    step = _step(tool="t", args={"x": "${steps.up.output.missing}"})
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "failed"
    assert "mapping error" in res.error


# ── agent step ────────────────────────────────────────────────────────────────


async def test_agent_host_run_text_output(monkeypatch):
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        assert messages[-1]["content"] == "sum hello"
        return "the answer"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    step = _step(id="a", type="agent", tool=None, prompt="sum ${steps.up.output.body}")
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "succeeded"
    assert res.output == {"text": "the answer"}


async def test_agent_named_uses_snapshot(monkeypatch):
    from fleetent.runtime import loop as agent_loop
    from fleetent.runtime import snapshot as snap_mod

    class Snap:
        system_prompt = "SP"
        allowed_tools = ["read_file"]
        model_policy = object()

    seen = {}

    async def fake_run(messages, **kw):
        seen["system"] = messages[0]["content"]
        seen["allowed_tools"] = kw.get("allowed_tools")
        return "ok"

    monkeypatch.setattr(snap_mod, "load_active", lambda name: Snap())
    monkeypatch.setattr(agent_loop, "run", fake_run)
    step = _step(id="a", type="agent", tool=None, agent="analyst", prompt="hi")
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "succeeded"
    assert seen["system"] == "SP"
    assert seen["allowed_tools"] == ["read_file"]


async def test_agent_missing_agent_fails(monkeypatch):
    from fleetent.runtime import snapshot as snap_mod

    monkeypatch.setattr(snap_mod, "load_active", lambda name: None)
    step = _step(id="a", type="agent", tool=None, agent="ghost", prompt="hi")
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "failed"
    assert "ghost" in res.error


async def test_agent_empty_reply_fails_closed(monkeypatch):
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return ""  # loop returns "" on awaiting_approval

    monkeypatch.setattr(agent_loop, "run", fake_run)
    step = _step(id="a", type="agent", tool=None, prompt="hi")
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "failed"
    assert "approval" in res.error or "no output" in res.error


# ── output_schema ─────────────────────────────────────────────────────────────


async def test_output_schema_success(monkeypatch):
    from fleetent.runtime import loop as agent_loop

    async def fake_run(messages, **kw):
        return '{"summary": "done"}'

    monkeypatch.setattr(agent_loop, "run", fake_run)
    step = _step(
        id="a",
        type="agent",
        tool=None,
        prompt="hi",
        output_schema={"type": "object", "required": ["summary"]},
    )
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.output == {"summary": "done"}


async def test_output_schema_retry_then_fallback(monkeypatch):
    from fleetent.runtime import loop as agent_loop

    calls = {"n": 0}

    async def fake_run(messages, **kw):
        calls["n"] += 1
        return "not json either"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    step = _step(
        id="a",
        type="agent",
        tool=None,
        prompt="hi",
        output_schema={"type": "object", "required": ["summary"]},
    )
    res = await execute_step(step, _CONTEXT, _ctx())
    assert calls["n"] == 2  # one retry
    assert res.status == "succeeded"
    assert res.output == {"text": "not json either"}


# ── notify step ───────────────────────────────────────────────────────────────


async def test_notify_explicit_target(monkeypatch):
    from fleetent.workflow import delivery

    sent = {}

    async def fake_send(target, text, connectors):
        sent["target"], sent["text"] = target, text
        return None

    monkeypatch.setattr(delivery, "send", fake_send)
    step = _step(
        id="n",
        type="notify",
        tool=None,
        text="hi ${inputs.channel}",
        to={"platform": "slack", "target": "C1"},
    )
    res = await execute_step(step, _CONTEXT, _ctx())
    assert res.status == "succeeded"
    assert sent["text"] == "hi #x"
    assert sent["target"][0] == "slack"


async def test_notify_no_target_fails():
    step = _step(id="n", type="notify", tool=None, text="hi")
    res = await execute_step(step, _CONTEXT, _ctx(origin=None))
    assert res.status == "failed"
    assert "target" in res.error


async def test_notify_fallback_to_origin(monkeypatch):
    from fleetent.workflow import delivery

    monkeypatch.setattr(
        delivery,
        "resolve_target",
        lambda to, origin: ("slack", "D1", "user", None) if origin else None,
    )
    sent = {}

    async def fake_send(target, text, connectors):
        sent["target"] = target
        return None

    monkeypatch.setattr(delivery, "send", fake_send)
    step = _step(id="n", type="notify", tool=None, text="hi")
    res = await execute_step(step, _CONTEXT, _ctx(origin={"platform": "slack", "chat_id": "D1"}))
    assert res.status == "succeeded"
    assert sent["target"] == ("slack", "D1", "user", None)
