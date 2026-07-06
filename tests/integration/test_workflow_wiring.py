"""Integration: agent_app boot wiring for the workflow engine + enabled toggle."""

import pytest


def _agent(enabled: bool):
    from fleetent.agent_config import AgentFile, default_models

    return AgentFile(
        name="a",
        version=1,
        models=default_models(),
        workflow={"enabled": enabled, "max_parallel": 3},
    )


async def test_engine_started_when_enabled(monkeypatch):
    from fleetent import workflow
    from fleetent.runtime import agent_app

    started = {"ok": False}

    async def fake_start(self):
        started["ok"] = True

    monkeypatch.setattr(workflow.WorkflowEngine, "start", fake_start)
    engine = await agent_app._start_workflow_engine(_agent(True))
    assert engine is not None
    assert workflow.is_enabled() is True
    assert workflow.get_engine() is engine
    assert started["ok"] is True
    assert engine._sem._value == 3  # max_parallel wired through


async def test_engine_not_started_when_disabled():
    from fleetent import workflow
    from fleetent.runtime import agent_app

    engine = await agent_app._start_workflow_engine(_agent(False))
    assert engine is None
    assert workflow.is_enabled() is False
    assert workflow.get_engine() is None


def test_store_wired_at_db_init(tmp_path):
    from fleetent.runtime import agent_app
    from fleetent.workflow import store

    agent_app._init_agent_db_schema(tmp_path / "data", agent_name="a")
    # store now usable end-to-end (table exists, handle injected)
    store.create_run(
        run_id="wfr-x",
        workflow_name="w",
        definition={"name": "w", "steps": [{"id": "s"}]},
        inputs={},
        principal=None,
        origin=None,
        deliver=None,
        step_ids=["s"],
    )
    assert store.get_run("wfr-x")["workflow_name"] == "w"
