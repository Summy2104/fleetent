"""Unit tests: KB connector sweep registered as cron interval job."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fleetent.cron_scheduler as cron_mod


def test_sweep_registered_as_interval_job():
    """_register_maintenance_jobs must add __kb_connector_sync_sweep__ interval job."""
    scheduler = cron_mod.CronScheduler()
    scheduler._scheduler = MagicMock()

    scheduler._register_maintenance_jobs()

    calls = scheduler._scheduler.add_job.call_args_list
    job_ids = [c.kwargs.get("id") or (c.args[2] if len(c.args) > 2 else None) for c in calls]
    # Flatten: add_job called with id as keyword
    kw_ids = [c.kwargs.get("id") for c in calls]
    assert "__kb_connector_sync_sweep__" in kw_ids


def test_sweep_registered_with_60s_default_interval():
    """Sweep must be registered with at least 60 seconds interval by default."""
    scheduler = cron_mod.CronScheduler()
    scheduler._scheduler = MagicMock()

    scheduler._register_maintenance_jobs()

    calls = scheduler._scheduler.add_job.call_args_list
    sweep_call = next(
        (c for c in calls if c.kwargs.get("id") == "__kb_connector_sync_sweep__"), None
    )
    assert sweep_call is not None
    assert sweep_call.kwargs.get("seconds", 0) >= 60
