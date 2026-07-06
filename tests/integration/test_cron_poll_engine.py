"""Tests for the durable next_run_at poll engine (cron-durable-poll-engine #2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import fleetent.cron_scheduler as cs
import fleetent.schedule_store as store
from fleetent.config import SchedulingSettings

_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _mk_interval_task(seconds: int = 60, next_run: datetime | None = None) -> dict:
    task = store.create(
        name="t",
        timezone="UTC",
        user_id="u-1",
        message="hi",
        source="tool",
        schedule_kind="interval",
        interval_seconds=seconds,
    )
    if next_run is not None:
        store.update_run_state(task["id"], next_run_at=_iso(next_run))
    return store.get(task["id"])


def _mk_cron_task(cron_expr: str = "0 12 * * *", next_run: datetime | None = None) -> dict:
    task = store.create(
        name="t",
        timezone="UTC",
        user_id="u-1",
        message="hi",
        source="tool",
        schedule_kind="cron",
        cron_expr=cron_expr,
    )
    if next_run is not None:
        store.update_run_state(task["id"], next_run_at=_iso(next_run))
    return store.get(task["id"])


# ── 3.1 due selection ────────────────────────────────────────────────────────


async def test_tick_selects_only_due_tasks(isolated_schedule_db, monkeypatch):
    fired: list[str] = []

    async def _fake_fire(row, connectors=None, history_retention=None):
        fired.append(row["id"])

    monkeypatch.setattr(cs, "_fire", _fake_fire)

    due = _mk_interval_task(60, next_run=_NOW - timedelta(seconds=1))
    _future = _mk_interval_task(60, next_run=_NOW + timedelta(seconds=120))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    assert fired == [due["id"]]
    assert _future["id"] not in fired


# ── 3.2 advance-before-execute + at-most-once claim ──────────────────────────


async def test_claim_next_run_is_at_most_once(isolated_schedule_db):
    task = _mk_interval_task(60, next_run=_NOW)
    old = task["next_run_at"]
    assert store.claim_next_run(task["id"], expected=old, new=_iso(_NOW + timedelta(seconds=60)))
    # a second claim with the same stale expected value loses (already advanced)
    assert not store.claim_next_run(
        task["id"], expected=old, new=_iso(_NOW + timedelta(seconds=999))
    )


async def test_once_task_next_run_not_advanced(isolated_schedule_db, monkeypatch):
    async def _fake_fire(row, connectors=None, history_retention=None):
        pass

    monkeypatch.setattr(cs, "_fire", _fake_fire)
    task = store.create(
        name="o",
        timezone="UTC",
        user_id="u-1",
        message="hi",
        source="tool",
        schedule_kind="once",
        run_at="2026-07-01T12:00:00+00:00",
    )
    store.update_run_state(task["id"], next_run_at=_iso(_NOW - timedelta(seconds=1)))
    before = store.get(task["id"])["next_run_at"]

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    # once is not advanced to a future occurrence (completion governs it, not advancement)
    assert store.get(task["id"])["next_run_at"] == before


# ── 3.3 slow run does not drop the next occurrence ───────────────────────────


async def test_slow_run_advances_next_run_before_completion(isolated_schedule_db, monkeypatch):
    release = asyncio.Event()

    async def _slow_fire(row, connectors=None, history_retention=None):
        await release.wait()

    monkeypatch.setattr(cs, "_fire", _slow_fire)

    task = _mk_interval_task(60, next_run=_NOW - timedelta(seconds=1))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)

    # next_run_at was advanced to the future BEFORE the (still-blocked) run finished,
    # so a subsequent tick would fire the next occurrence rather than dropping it.
    advanced = store.get(task["id"])["next_run_at"]
    assert datetime.fromisoformat(advanced) > _NOW

    release.set()
    await asyncio.gather(*dispatched)


# ── 3.4 stale schedule fast-forwards, at most once ───────────────────────────


async def test_stale_interval_fast_forwards_single_fire(isolated_schedule_db, monkeypatch):
    fired: list[str] = []

    async def _fake_fire(row, connectors=None, history_retention=None):
        fired.append(row["id"])

    monkeypatch.setattr(cs, "_fire", _fake_fire)

    # next_run 10 minutes in the past for a 60s interval == 10 missed slots.
    task = _mk_interval_task(60, next_run=_NOW - timedelta(minutes=10))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    # fired at most once (not once per missed slot) and fast-forwarded to the future
    assert fired == [task["id"]]
    assert datetime.fromisoformat(store.get(task["id"])["next_run_at"]) > _NOW


# ── 3.5 misfire grace: cron gets an upper bound, interval never does (cron-hardening F5) ──


async def test_cron_within_grace_still_fires(isolated_schedule_db, monkeypatch):
    """A daily cron (24h period, grace = min(12h, 2h) = 2h) that is only 40 minutes
    late still fires — well within its misfire grace window."""
    fired: list[str] = []

    async def _fake_fire(row, connectors=None, history_retention=None):
        fired.append(row["id"])

    monkeypatch.setattr(cs, "_fire", _fake_fire)

    task = _mk_cron_task("0 12 * * *", next_run=_NOW - timedelta(minutes=40))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    assert fired == [task["id"]]
    assert store.list_runs(task["id"]) == []  # no "missed" row — this is a normal fire


async def test_cron_beyond_grace_is_missed_not_fired(isolated_schedule_db, monkeypatch):
    """A daily cron missed by 3 days (>> its 2h grace cap) must NOT fire a stale
    occurrence — it fast-forwards and records a `missed` history row instead."""
    fired: list[str] = []

    async def _fake_fire(row, connectors=None, history_retention=None):
        fired.append(row["id"])

    monkeypatch.setattr(cs, "_fire", _fake_fire)

    task = _mk_cron_task("0 12 * * *", next_run=_NOW - timedelta(days=3))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    assert fired == []  # not dispatched
    assert datetime.fromisoformat(store.get(task["id"])["next_run_at"]) > _NOW  # fast-forwarded

    runs = store.list_runs(task["id"])
    assert len(runs) == 1
    assert runs[0]["status"] == "missed"


async def test_interval_beyond_2h_still_fires_no_grace_cap(isolated_schedule_db, monkeypatch):
    """Interval tasks have no staleness upper bound — a fixed-period task's single
    catch-up fire is always current-value content, unlike a stale cron digest."""
    fired: list[str] = []

    async def _fake_fire(row, connectors=None, history_retention=None):
        fired.append(row["id"])

    monkeypatch.setattr(cs, "_fire", _fake_fire)

    task = _mk_interval_task(60, next_run=_NOW - timedelta(days=3))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.gather(*dispatched)

    assert fired == [task["id"]]


# ── 4.1 bounded parallel execution ───────────────────────────────────────────


async def test_bounded_parallel_execution(isolated_schedule_db, monkeypatch):
    concurrent = 0
    peak = 0
    gate = asyncio.Event()

    async def _tracking_fire(row, connectors=None, history_retention=None):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await gate.wait()
        concurrent -= 1

    monkeypatch.setattr(cs, "_fire", _tracking_fire)

    for _ in range(4):
        _mk_interval_task(60, next_run=_NOW - timedelta(seconds=1))

    sched = cs.CronScheduler(settings=SchedulingSettings(max_parallel=2))
    for t in store.list_tasks():
        sched._register(t)
    dispatched = await sched._tick(now=_NOW)
    await asyncio.sleep(0.05)  # let dispatched runs reach the gate

    assert peak <= 2  # concurrency bound honored

    gate.set()
    await asyncio.gather(*dispatched)


# ── 4.2 tick loop lifecycle ──────────────────────────────────────────────────


async def test_start_starts_tick_and_shutdown_stops(isolated_schedule_db):
    sched = cs.CronScheduler(settings=SchedulingSettings(tick_interval_seconds=0.05))
    await sched.start()
    assert sched.running
    assert cs.current() is sched
    await sched.shutdown()
    assert not sched.running
    assert cs.current() is None


async def test_disabled_scheduling_does_not_start_tick(isolated_schedule_db):
    sched = cs.CronScheduler(settings=SchedulingSettings(enabled=False))
    await sched.start()
    assert not sched.running


# ── 5. through-path: real store + real _fire, only _agent_run stubbed ────────
# (fix-cron-store-and-once F1 — AAA-8288: the mock boundary that previously hid
# the update_run_state clobber bug. Only the LLM call is stubbed; store, _fire,
# _record_run, _record_history, claim_next_run, and session persistence are real.)


async def test_real_fire_preserves_grid_across_repeated_fires(
    isolated_schedule_db, monkeypatch, tmp_path
):
    """An interval task fired repeatedly through the real _fire path must not drift:
    each fire's post-run writeback must preserve the next_run_at the tick already
    claimed, not clobber it back to NULL (which forced a stale re-anchor and
    cumulative drift ~= run duration + tick interval per occurrence)."""
    from unittest.mock import AsyncMock

    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_agent_run", AsyncMock(return_value="[SILENT]"))

    task = store.create(
        name="t",
        timezone="UTC",
        user_id="default",
        message="hi",
        source="tool",
        schedule_kind="interval",
        interval_seconds=60,
    )
    store.update_run_state(task["id"], next_run_at=_iso(_NOW))

    sched = cs.CronScheduler(settings=SchedulingSettings())
    sched._register(store.get(task["id"]))

    now = _NOW
    expected_next = _NOW
    for _ in range(5):
        expected_next = expected_next + timedelta(seconds=60)
        dispatched = await sched._tick(now=now)
        await asyncio.gather(*dispatched)

        row = store.get(task["id"])
        assert row["next_run_at"] == _iso(expected_next), (
            "next_run_at drifted off the fixed grid after a real fire — "
            "the post-fire writeback clobbered the claimed value"
        )
        assert row["last_status"] == "ok", "last_status did not survive the writeback"

        now = now + timedelta(seconds=60)
