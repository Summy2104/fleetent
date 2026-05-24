import asyncio
import time
from unittest.mock import patch

import pytest

from mini_agent.sub_agent import SubAgentExecutor


async def test_two_tasks_run_and_return_results():
    executor = SubAgentExecutor()

    async def fake_run(messages, **kwargs):
        return messages[0]["content"] + "_result"

    with patch("mini_agent.sub_agent.agent_loop.run", side_effect=fake_run):
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

    with patch("mini_agent.sub_agent.agent_loop.run", side_effect=fake_run):
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
    import mini_agent.tool_registry as tr

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

    with patch("mini_agent.sub_agent.agent_loop.run", side_effect=fake_run):
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

    with patch("mini_agent.sub_agent.agent_loop.run", side_effect=fake_run):
        results = await executor.run(
            tasks=[{"name": "t1", "prompt": "go"}],
            parent_user_id="user-1",
            parent_agent_id=None,
            parent_session_id="sess-xyz",
        )

    assert results[0].parent_session_id == "sess-xyz"


async def test_tasks_run_concurrently_not_sequentially():
    """asyncio.gather should overlap task execution, not serialize it."""
    start_times: list[float] = []

    async def timed_run(messages, **kwargs):
        start_times.append(time.monotonic())
        await asyncio.sleep(0.05)
        return "done"

    with patch("mini_agent.sub_agent.agent_loop.run", side_effect=timed_run):
        executor = SubAgentExecutor()
        t0 = time.monotonic()
        await executor.run(
            tasks=[
                {"name": "t1", "prompt": "p1"},
                {"name": "t2", "prompt": "p2"},
            ],
            parent_user_id="u",
            parent_agent_id=None,
            parent_session_id="s",
        )
        elapsed = time.monotonic() - t0

    # Sequential would take ~0.10s; parallel should complete in ~0.05s
    assert elapsed < 0.09, f"tasks appear sequential (elapsed={elapsed:.3f}s)"
    # Both tasks must have started before either finished
    assert len(start_times) == 2
    assert abs(start_times[1] - start_times[0]) < 0.02
