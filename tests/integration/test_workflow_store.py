"""DB-backed workflow store tests.

workflow_runs / workflow_step_runs are created by the unified AGENT_STATE_MIGRATIONS
on the per-agent agent_state.db; tests inject that migrated handle (no platform).
"""

import pytest


def _bind(tmp_path, agent_id="agent"):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter
    from fleetent.workflow import store

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    store.set_state_db(db)
    return store, db


def _start(store, run_id="wfr-1", steps=("a", "b")):
    store.create_run(
        run_id=run_id,
        workflow_name="demo",
        definition={"name": "demo", "steps": [{"id": s} for s in steps]},
        inputs={"channel": "#x"},
        principal={"user_id": "u1"},
        origin={"platform": "cli"},
        deliver=None,
        step_ids=list(steps),
    )


def test_migrations_create_tables_and_crud(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    run = store.get_run("wfr-1")
    assert run["status"] == "pending"
    # frozen definition + principal round-trip
    assert run["definition"]["name"] == "demo"
    assert run["principal"] == {"user_id": "u1"}
    assert run["inputs"] == {"channel": "#x"}
    steps = store.list_steps("wfr-1")
    assert {s["step_id"] for s in steps} == {"a", "b"}
    assert all(s["status"] == "pending" and s["attempt"] == 1 for s in steps)


def test_no_platform_import_in_store():
    import fleetent.workflow.store as store_mod
    import inspect

    src = inspect.getsource(store_mod)
    assert "fleetent.platform" not in src


def test_run_status_transition_and_terminal_immutable(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    store.set_run_status("wfr-1", "running", started_at="2026-01-01T00:00:00Z")
    store.set_run_status("wfr-1", "succeeded", ended_at="2026-01-01T00:01:00Z")
    assert store.get_run("wfr-1")["status"] == "succeeded"
    with pytest.raises(Exception, match="terminal|illegal"):
        store.set_run_status("wfr-1", "running")


def test_step_finish_terminal_immutable(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    assert store.claim_step("wfr-1", "a", 1) is True
    store.finish_step("wfr-1", "a", 1, status="succeeded", output={"text": "ok"})
    assert store.get_step("wfr-1", "a")["output"] == {"text": "ok"}
    with pytest.raises(Exception, match="terminal|illegal"):
        store.finish_step("wfr-1", "a", 1, status="failed", error="x")


def test_claim_is_idempotent(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    first = store.claim_step("wfr-1", "a", 1)
    second = store.claim_step("wfr-1", "a", 1)  # already running → lost
    assert first is True
    assert second is False


def test_reclaim_expired_opens_next_attempt(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    store.claim_step("wfr-1", "a", 1, now="2026-01-01T00:00:00Z")
    new_attempt = store.reclaim_expired_step("wfr-1", "a", 1)
    assert new_attempt == 2
    # old attempt failed, new attempt pending
    assert store.get_step("wfr-1", "a", 1)["status"] == "failed"
    latest = store.get_step("wfr-1", "a")
    assert latest["attempt"] == 2 and latest["status"] == "pending"
    # a fresh claim on the new attempt succeeds
    assert store.claim_step("wfr-1", "a", 2) is True


def test_skip_step_cascade(tmp_path):
    store, _ = _bind(tmp_path)
    _start(store)
    store.skip_step("wfr-1", "b")
    assert store.get_step("wfr-1", "b")["status"] == "skipped"


def test_prune_runs_retention(tmp_path):
    store, _ = _bind(tmp_path)
    for i in range(5):
        _start(store, run_id=f"wfr-{i}", steps=("a",))
        store.set_run_status(f"wfr-{i}", "running")
        store.set_run_status(f"wfr-{i}", "succeeded")
    store.prune_runs("demo", retention=2)
    assert len(store.list_runs("demo")) == 2
