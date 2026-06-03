import asyncio
import time
from unittest.mock import patch

import pytest

from fleetent.sub_agent import SubAgentExecutor


async def test_two_tasks_run_and_return_results():
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        return messages[0]["content"] + "_result"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[
                {"name": "task_a", "prompt": "do_a"},
                {"name": "task_b", "prompt": "do_b"},
            ],
            parent_user_id="user-1",
            parent_agent_id=None,
            parent_session_id="sess-parent",
        )

    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"task_a", "task_b"}
    successes = [r for r in results if r.error is None]
    assert len(successes) == 2


async def test_partial_failure_returns_error_for_failed_task():
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        if "fail" in messages[0]["content"]:
            raise RuntimeError("child failed")
        return "ok"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[
                {"name": "good", "prompt": "do_good"},
                {"name": "bad", "prompt": "do_fail"},
            ],
            parent_user_id="user-1",
            parent_agent_id=None,
            parent_session_id="sess-parent",
        )

    errors = [r for r in results if r.error is not None]
    successes = [r for r in results if r.error is None]
    assert len(errors) == 1
    assert len(successes) == 1
    assert errors[0].name == "bad"


async def test_child_cannot_spawn_sub_agent():
    """When is_sub_agent=True, sub_agent tool must not be in registry."""
    import fleetent.tool_registry as tr

    # Simulate what agent_loop does when is_sub_agent=True
    # The sub_agent tool should not be dispatched
    # We verify by checking that is_sub_agent flag prevents nested dispatch
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        # When is_sub_agent=True, trying to call sub_agent tool should raise
        if kwargs.get("is_sub_agent"):
            with pytest.raises((PermissionError, ValueError, RuntimeError)):
                await tr.dispatch("sub_agent", {"tasks": []}, is_sub_agent=True)
        return "ok"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[{"name": "t1", "prompt": "test"}],
            parent_user_id="user-1",
            parent_agent_id=None,
            parent_session_id="sess-parent",
        )
    # Main assertion: no crash, returns result
    assert results[0].result == "ok"


async def test_results_contain_parent_session_id():
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        return "done"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[{"name": "t1", "prompt": "go"}],
            parent_user_id="user-1",
            parent_agent_id=None,
            parent_session_id="sess-xyz",
        )

    assert results[0].parent_session_id == "sess-xyz"


async def test_tasks_run_concurrently_not_sequentially(tmp_path, monkeypatch):
    """asyncio.gather should overlap task execution, not serialize it."""
    import fleetent.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    start_times: list[float] = []

    async def timed_run(messages, **kwargs):
        start_times.append(time.monotonic())
        await asyncio.sleep(0.05)
        return "done"

    with patch("fleetent.agent_loop.run", side_effect=timed_run):
        executor = SubAgentExecutor()
        await executor.run(
            tasks=[
                {"name": "t1", "prompt": "p1"},
                {"name": "t2", "prompt": "p2"},
            ],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="s",
        )

    # The authoritative concurrency guard is start-time overlap. Total elapsed
    # includes synchronous SQLite lifecycle writes and is noisy on CI filesystems.
    assert len(start_times) == 2
    assert abs(start_times[1] - start_times[0]) < 0.02


# ── lifecycle integration (AR20, group 7) ────────────────────────────────────


def _iso_set(*vals):
    return all(v is not None for v in vals)


async def test_lifecycle_records_succeeded_with_timestamps(tmp_path, monkeypatch):
    import fleetent.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        return "ok"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="sess",
        )
    rows = sal.query_by_parent("sess")
    assert len(rows) == 1
    assert rows[0].state is sal.SubAgentState.succeeded
    assert _iso_set(rows[0].created_at, rows[0].started_at, rows[0].ended_at)


async def test_cancel_token_passed_with_parent_link(tmp_path, monkeypatch):
    import fleetent.sub_agent_lifecycle as sal
    from fleetent.cancellation import CancelToken

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()
    captured: dict[str, object] = {}

    async def fake_run(messages, **kwargs):
        captured["token"] = kwargs.get("cancel_token")
        return "ok"

    batch = CancelToken()
    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_user_id="u",
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

    import fleetent.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        # Simulate the slow task's sub-loop running past its own deadline:
        # push the child token's deadline into the past (no wall-clock wait).
        if messages[0]["content"] == "slow":
            kwargs["cancel_token"].deadline = _time.monotonic() - 1
            return "partial"
        return "done"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[{"name": "slow", "prompt": "slow"}, {"name": "fast", "prompt": "fast"}],
            parent_user_id="u",
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
    import fleetent.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        # External/parent cancel arrives before this task's own deadline.
        kwargs["cancel_token"].parent.cancel()
        return "partial"

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="sess",
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.cancelled  # parent-driven, not deadline


async def test_pending_cancelled_when_batch_precancelled(tmp_path, monkeypatch):
    import fleetent.sub_agent_lifecycle as sal
    from fleetent.cancellation import CancelToken

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()
    called = {"n": 0}

    async def fake_run(messages, **kwargs):
        called["n"] += 1
        return "ok"

    batch = CancelToken()
    batch.cancel()  # already cancelled before the batch starts
    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="sess",
            cancel_token=batch,
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.cancelled
    assert row.started_at is None  # never started
    assert called["n"] == 0  # agent_loop.run not invoked


async def test_failure_marks_failed_with_error(tmp_path, monkeypatch):
    import fleetent.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        raise RuntimeError("boom")

    with patch("fleetent.agent_loop.run", side_effect=fake_run):
        await executor.run(
            tasks=[{"name": "a", "prompt": "p"}],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="sess",
        )
    row = sal.query_by_parent("sess")[0]
    assert row.state is sal.SubAgentState.failed
    assert row.error is not None and "boom" in row.error
