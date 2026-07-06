"""Unit tests for run_workflow / workflow_status builtin tools (mocked engine/store)."""

import pytest

import fleetent.tools  # noqa: F401 — trigger builtin tool registration side effect


def test_tools_registered():
    from fleetent.tools import registry

    assert registry.is_registered("run_workflow")
    assert registry.is_registered("workflow_status")


def test_availability_gated_by_enabled(monkeypatch):
    from fleetent import workflow
    from fleetent.tools import registry

    monkeypatch.setattr(workflow, "is_enabled", lambda: False)
    monkeypatch.setattr(workflow, "get_engine", lambda: object())
    names = {s["function"]["name"] for s in registry.get_schemas()}
    assert "run_workflow" not in names

    monkeypatch.setattr(workflow, "is_enabled", lambda: True)
    names = {s["function"]["name"] for s in registry.get_schemas()}
    assert "run_workflow" in names


async def test_run_workflow_starts_and_returns_run_id(monkeypatch):
    from fleetent import workflow
    from fleetent.tools.builtin_tools import run_workflow
    from fleetent.tools.registry import ToolContext

    class FakeEngine:
        def __init__(self):
            self.spawned = None

        def start_run(self, wf, **kw):
            self.started = kw
            return "wfr-abc"

        def spawn(self, run_id):
            self.spawned = run_id

    eng = FakeEngine()
    monkeypatch.setattr(workflow, "get_engine", lambda: eng)
    monkeypatch.setattr(workflow, "load_definition", lambda name: object())

    from fleetent.identity import Principal

    tc = ToolContext(principal=Principal(user_id="u1", tenant_id="t1"))
    out = await run_workflow("demo", '{"channel": "#x"}', tool_context=tc)
    assert "wfr-abc" in out
    assert eng.spawned == "wfr-abc"
    assert eng.started["inputs"] == {"channel": "#x"}
    assert eng.started["principal"] == {"user_id": "u1", "tenant_id": "t1"}


async def test_run_workflow_unknown_lists_available(monkeypatch):
    from fleetent import workflow
    from fleetent.tools.builtin_tools import run_workflow

    def raise_nf(name):
        raise workflow.WorkflowNotFoundError("workflow 'ghost' not found; available: ['demo']")

    monkeypatch.setattr(workflow, "get_engine", lambda: object())
    monkeypatch.setattr(workflow, "load_definition", raise_nf)
    out = await run_workflow("ghost", "{}")
    assert "ghost" in out and "demo" in out


async def test_run_workflow_missing_input_rejected(monkeypatch):
    from fleetent import workflow
    from fleetent.tools.builtin_tools import run_workflow

    class FakeEngine:
        def start_run(self, wf, **kw):
            raise workflow.WorkflowInputError("missing required input 'channel'")

        def spawn(self, run_id):  # pragma: no cover — must not be reached
            raise AssertionError("spawn must not run when start_run rejects")

    monkeypatch.setattr(workflow, "get_engine", lambda: FakeEngine())
    monkeypatch.setattr(workflow, "load_definition", lambda name: object())
    out = await run_workflow("demo", "{}")
    assert "channel" in out


async def test_run_workflow_bad_json_inputs(monkeypatch):
    from fleetent import workflow
    from fleetent.tools.builtin_tools import run_workflow

    monkeypatch.setattr(workflow, "get_engine", lambda: object())
    monkeypatch.setattr(workflow, "load_definition", lambda name: object())
    out = await run_workflow("demo", "{not json")
    assert "invalid inputs JSON" in out


def test_workflow_status_summary(monkeypatch):
    from fleetent.tools.builtin_tools import workflow_status
    from fleetent.workflow import store

    monkeypatch.setattr(
        store, "get_run", lambda rid: {"status": "running", "workflow_name": "demo"}
    )
    monkeypatch.setattr(
        store,
        "list_steps",
        lambda rid: [
            {"step_id": "a", "status": "succeeded", "error": None},
            {"step_id": "b", "status": "failed", "error": "boom"},
        ],
    )
    out = workflow_status("wfr-1")
    assert "running" in out and "a [succeeded]" in out and "boom" in out


def test_workflow_status_not_found(monkeypatch):
    from fleetent.tools.builtin_tools import workflow_status
    from fleetent.workflow import store

    monkeypatch.setattr(store, "get_run", lambda rid: None)
    assert "not found" in workflow_status("ghost")
