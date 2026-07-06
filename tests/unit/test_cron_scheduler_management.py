from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import cron_scheduler
from fleetent.config import SchedulingSettings


def test_record_run_swallow_store_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cron_scheduler._store,
        "update_run_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    cron_scheduler._record_run({"id": "task-1"}, "2026-06-15T00:00:00Z", "ok", None)  # noqa: SLF001


def test_record_history_swallow_store_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # A run-history write failure must never break a fire (best-effort side channel).
    monkeypatch.setattr(
        cron_scheduler._store,
        "record_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    cron_scheduler._record_history(  # noqa: SLF001
        {"id": "task-1"}, "2026-06-15T00:00:00Z", "ok", kind="generate"
    )


async def test_scheduler_start_skips_disabled_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = cron_scheduler.CronScheduler(settings=SchedulingSettings(enabled=False))
    monkeypatch.setattr(
        cron_scheduler._store, "list_tasks", lambda: (_ for _ in ()).throw(AssertionError)
    )

    await scheduler.start()

    assert scheduler.running is False
    assert cron_scheduler.current() is None
    await scheduler.shutdown()


async def test_scheduler_start_bulkheads_bad_rows_and_sets_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = [{"id": "good"}, {"id": "bad"}]
    disabled: list[tuple[str, bool]] = []
    registered: list[str] = []

    monkeypatch.setattr(cron_scheduler._store, "list_tasks", lambda: tasks)
    monkeypatch.setattr(
        cron_scheduler._store,
        "set_enabled",
        lambda task_id, enabled: disabled.append((task_id, enabled)),
    )
    monkeypatch.setattr(
        cron_scheduler.CronScheduler,
        "_register_maintenance_jobs",
        lambda self: registered.append("maintenance"),
    )

    def fake_register(self, task):
        registered.append(task["id"])
        if task["id"] == "bad":
            raise ValueError("broken")

    monkeypatch.setattr(cron_scheduler.CronScheduler, "_register", fake_register)

    scheduler = cron_scheduler.CronScheduler()
    await scheduler.start()

    assert registered == ["good", "bad", "maintenance"]
    assert disabled == [("bad", False)]
    assert scheduler.running is True
    assert cron_scheduler.current() is scheduler
    await scheduler.shutdown()


def test_register_maintenance_jobs_adds_cleanup_job() -> None:
    scheduler = cron_scheduler.CronScheduler()

    scheduler._register_maintenance_jobs()  # noqa: SLF001

    view = scheduler.get_job("__maintenance_spillover_cleanup__")
    assert view is not None
    assert view.next_run_time is not None  # scheduled for the next 03:00


@pytest.mark.parametrize(
    "task",
    [
        {"id": "once-1", "schedule_kind": "once", "run_at": "2099-06-15T08:00:00+00:00"},
        {"id": "int-1", "schedule_kind": "interval", "interval_seconds": 30},
        {"id": "cron-1", "schedule_kind": "cron", "cron_expr": "0 9 * * *"},
    ],
)
def test_register_sets_next_run_for_each_kind(task: dict[str, object]) -> None:
    # The poll engine registers a job view with a computed next_run_time (no APScheduler
    # trigger). The store write is best-effort and suppressed when no state DB is present.
    scheduler = cron_scheduler.CronScheduler()

    scheduler._register(task)  # noqa: SLF001

    view = scheduler.get_job(str(task["id"]))
    assert view is not None
    assert view.next_run_time is not None


def test_create_remove_and_toggle_task_delegate_to_store_and_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = cron_scheduler.CronScheduler()
    task = {"id": "task-1", "schedule_kind": "cron", "cron_expr": "0 9 * * *"}
    monkeypatch.setattr(cron_scheduler._store, "create", lambda **kwargs: task)
    monkeypatch.setattr(cron_scheduler._store, "delete", lambda task_id: task_id == "task-1")
    monkeypatch.setattr(cron_scheduler._store, "set_enabled", lambda task_id, enabled: True)
    monkeypatch.setattr(
        cron_scheduler._store, "get", lambda task_id: task if task_id == "task-1" else None
    )
    registered: list[str] = []
    removed: list[str] = []
    monkeypatch.setattr(
        cron_scheduler.CronScheduler, "_register", lambda self, row: registered.append(row["id"])
    )
    monkeypatch.setattr(
        cron_scheduler.CronScheduler, "remove_job", lambda self, tid: removed.append(tid)
    )

    created = scheduler.create_task(name="n", cron_expr="0 9 * * *")
    removed_ok = scheduler.remove_task("task-1")
    enabled = scheduler.set_task_enabled("task-1", True)
    disabled = scheduler.set_task_enabled("task-1", False)

    assert created == task
    assert removed_ok is True
    assert enabled is True
    assert disabled is True
    assert registered == ["task-1", "task-1"]  # create + resume re-register
    assert removed == ["task-1", "task-1"]  # remove_task + disable deregister


def test_complete_once_closes_both_outcomes_but_only_writes_completed_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fix-cron-store-and-once F2a: a failed once is terminally closed (enabled=0)
    same as a successful one — it must never stay due for automatic hot retry — but
    only the success path overwrites last_status to "completed"; a failure keeps its
    recorded error state as-is (no update_run_state call for it)."""
    scheduler = cron_scheduler.CronScheduler()
    updates: list[tuple[str, dict[str, object]]] = []
    states = {
        "ok": {"id": "ok", "last_status": "ok", "last_run_at": "now"},
        "fail": {"id": "fail", "last_status": "error", "last_run_at": "now"},
    }
    monkeypatch.setattr(cron_scheduler._store, "get", lambda task_id: states.get(task_id))
    monkeypatch.setattr(
        cron_scheduler._store,
        "set_enabled",
        lambda task_id, enabled: updates.append((task_id, {"enabled": enabled})),
    )
    monkeypatch.setattr(
        cron_scheduler._store,
        "update_run_state",
        lambda task_id, **kwargs: updates.append((task_id, kwargs)),
    )

    scheduler._complete_once("missing")  # noqa: SLF001
    scheduler._complete_once("fail")  # noqa: SLF001
    scheduler._complete_once("ok")  # noqa: SLF001

    assert updates == [
        ("fail", {"enabled": False}),
        ("ok", {"enabled": False}),
        ("ok", {"last_run_at": "now", "last_status": "completed", "last_error": None}),
    ]


async def test_run_now_and_module_run_task_now_cover_scheduler_and_store_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = cron_scheduler.CronScheduler(connectors_resolver=lambda: {"slack": object()})
    fire = AsyncMock()
    monkeypatch.setattr(cron_scheduler, "_fire", fire)
    monkeypatch.setattr(
        cron_scheduler._store,
        "get",
        lambda task_id: {"id": task_id} if task_id == "task-1" else None,
    )
    monkeypatch.setattr(cron_scheduler, "_current", scheduler)

    assert await scheduler.run_now("missing") is False
    assert await scheduler.run_now("task-1") is True
    fire.assert_awaited_once()

    monkeypatch.setattr(cron_scheduler, "_current", None)
    fire.reset_mock()
    assert await cron_scheduler.run_task_now("missing") is False
    assert await cron_scheduler.run_task_now("task-1") is True
    fire.assert_awaited_once_with({"id": "task-1"})


def test_module_facade_functions_cover_scheduler_and_store_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = SimpleNamespace(
        create_task=lambda **kwargs: {"via": "scheduler", **kwargs},
        remove_task=lambda task_id: task_id == "task-1",
        set_task_enabled=lambda task_id, enabled: enabled,
    )
    monkeypatch.setattr(cron_scheduler, "_current", scheduler)
    monkeypatch.setattr(
        cron_scheduler,
        "_parse_run_at",
        lambda value, tz=None: datetime(2026, 6, 15, tzinfo=UTC),
    )

    created = cron_scheduler.create_task(
        name="n", schedule_kind="run_at", run_at="2026-06-15 08:00:00 UTC"
    )
    assert created["schedule_kind"] == "once"
    assert created["run_at"] == "2026-06-15T00:00:00+00:00" or created["run_at"].endswith("+00:00")
    assert cron_scheduler.remove_task("task-1") is True
    assert cron_scheduler.set_task_enabled("task-1", True) is True

    monkeypatch.setattr(cron_scheduler, "_current", None)
    monkeypatch.setattr(
        cron_scheduler._store, "create", lambda **kwargs: {"via": "store", **kwargs}
    )
    monkeypatch.setattr(cron_scheduler._store, "delete", lambda task_id: False)
    monkeypatch.setattr(cron_scheduler._store, "set_enabled", lambda task_id, enabled: False)
    monkeypatch.setattr(
        cron_scheduler._store,
        "list_tasks",
        lambda include_disabled=False: [{"id": "x", "include_disabled": include_disabled}],
    )

    assert cron_scheduler.create_task(name="n")["via"] == "store"
    assert cron_scheduler.remove_task("missing") is False
    assert cron_scheduler.set_task_enabled("missing", False) is False
    assert cron_scheduler.list_tasks(include_disabled=True) == [
        {"id": "x", "include_disabled": True}
    ]


def test_parse_cron_splits_expression() -> None:
    assert cron_scheduler._parse_cron("*/5 9 * * 1-5") == {  # noqa: SLF001
        "minute": "*/5",
        "hour": "9",
        "day": "*",
        "month": "*",
        "day_of_week": "1-5",
    }
