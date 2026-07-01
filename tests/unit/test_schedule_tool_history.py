"""Unit tests for the schedule tool `history` action (cron-run-history #3)."""

from __future__ import annotations

from fleetent.tools import builtin_tools


async def test_history_action_returns_recent_runs(monkeypatch) -> None:
    monkeypatch.setattr(
        "fleetent.cron_scheduler.list_runs",
        lambda task_id, limit=20: [
            {
                "fired_at": "2026-07-01T00:01:00Z",
                "status": "error",
                "agent_error": None,
                "delivery_error": "slack down",
                "duration_ms": 1200,
            },
            {
                "fired_at": "2026-07-01T00:00:00Z",
                "status": "ok",
                "agent_error": None,
                "delivery_error": None,
                "duration_ms": 800,
            },
        ],
    )

    out = await builtin_tools.schedule(action="history", task_id="task-1")

    assert "2026-07-01T00:01:00Z" in out
    assert "error" in out
    assert "slack down" in out
    assert "2026-07-01T00:00:00Z" in out
    assert "ok" in out


async def test_history_action_unknown_task_returns_error(monkeypatch) -> None:
    monkeypatch.setattr("fleetent.cron_scheduler.list_runs", lambda task_id, limit=20: [])
    monkeypatch.setattr("fleetent.cron_scheduler.list_tasks", lambda include_disabled=True: [])

    out = await builtin_tools.schedule(action="history", task_id="nope")

    assert out.startswith("error:")
    assert "nope" in out


async def test_history_action_no_runs_yet(monkeypatch) -> None:
    monkeypatch.setattr(
        "fleetent.cron_scheduler.list_runs",
        lambda task_id, limit=20: [],
    )
    # A known task with no runs yet is not an error.
    monkeypatch.setattr(
        "fleetent.cron_scheduler.list_tasks",
        lambda include_disabled=True: [{"id": "task-1"}],
    )

    out = await builtin_tools.schedule(action="history", task_id="task-1")

    assert "no runs" in out.lower()
