"""DB-backed sub-agent executor lifecycle integration tests."""

import asyncio
import time
from unittest.mock import patch

from fleetent.runtime.sub_agent import SubAgentExecutor


def _bind_state_db(sal, tmp_path):
    """Inject a migrated per-agent agent_state.db (replaces the old DB_PATH monkeypatch)."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", "agent").open_state_db(MIGRATIONS)
    sal.set_state_db(db)
    return db


async def test_tasks_run_concurrently_not_sequentially(tmp_path, monkeypatch):
    """asyncio.gather should overlap task execution, not serialize it."""
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    start_times: list[float] = []

    async def timed_run(messages, **kwargs):
        start_times.append(time.monotonic())
        await asyncio.sleep(0.05)
        return "done"

    with patch("fleetent.runtime.loop.run", side_effect=timed_run):
        executor = SubAgentExecutor()
        await executor.run(
            tasks=[
                {"name": "t1", "prompt": "p1"},
                {"name": "t2", "prompt": "p2"},
            ],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="s",
        )

    # The authoritative concurrency guard is start-time overlap. Total elapsed
    # includes synchronous SQLite lifecycle writes and is noisy on CI filesystems.
    assert len(start_times) == 2
    assert abs(start_times[1] - start_times[0]) < 0.02


def _iso_set(*vals):
    return all(v is not None for v in vals)


async def test_lifecycle_records_succeeded_with_timestamps(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        return "ok"

    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
        )
    rows = sal.query_by_parent("sess")
    assert len(rows) == 1
    assert rows[0].state is sal.SubAgentState.succeeded
    assert _iso_set(rows[0].created_at, rows[0].started_at, rows[0].ended_at)


async def test_cancel_token_passed_with_parent_link(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal
    from fleetent.runtime.cancellation import CancelToken

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()
    captured: dict[str, object] = {}

    async def fake_run(messages, **kwargs):
        captured["token"] = kwargs.get("cancel_token")
        return "ok"

    batch = CancelToken()
    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
            cancel_token=batch,
        )
    tok = captured["token"]
    assert isinstance(tok, CancelToken)
    assert tok.deadline is not None  # per-tool deadline set
    assert tok.parent is batch  # linked to the batch/external token


async def test_one_task_times_out_others_succeed(tmp_path, monkeypatch):
    import time as _time

    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        # Simulate the slow task's sub-loop running past its own deadline:
        # push the child token's deadline into the past (no wall-clock wait).
        if messages[0]["content"] == "slow":
            kwargs["cancel_token"].deadline = _time.monotonic() - 1
            return "partial"
        return "done"

    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[{"name": "slow", "prompt": "slow"}, {"name": "fast", "prompt": "fast"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
        )
    assert len(results) == 2  # one task's timeout does not break the gather
    by_name = {r.run_id if False else r.name: r for r in results}
    assert set(by_name) == {"slow", "fast"}
    states = {r.name: r.state for r in sal.query_by_parent("sess")}
    assert states["slow"] is sal.SubAgentState.timed_out
    assert states["fast"] is sal.SubAgentState.succeeded


async def test_parent_cancel_marks_cancelled(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        # External/parent cancel arrives before this task's own deadline.
        kwargs["cancel_token"].parent.cancel()
        return "partial"

    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.cancelled  # parent-driven, not deadline


async def test_pending_cancelled_when_batch_precancelled(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal
    from fleetent.runtime.cancellation import CancelToken

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()
    called = {"n": 0}

    async def fake_run(messages, **kwargs):
        called["n"] += 1
        return "ok"

    batch = CancelToken()
    batch.cancel()  # already cancelled before the batch starts
    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
            cancel_token=batch,
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.cancelled
    assert row.started_at is None  # never started
    assert called["n"] == 0  # agent_loop.run not invoked


async def test_failure_marks_failed_with_error(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        raise RuntimeError("boom")

    with patch("fleetent.runtime.loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_principal=None,
            parent_agent_id=None,
            parent_session_id="sess",
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.failed
    assert row.error is not None and "boom" in row.error
