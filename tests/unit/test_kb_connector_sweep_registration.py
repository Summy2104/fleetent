"""Unit tests: KB connector sweep registered as platform maintenance interval job."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_sweep_registered_as_interval_job():
    """_build_platform_maintenance_scheduler must add __kb_connector_sync_sweep__ job."""
    from fleetent.config import SchedulingSettings
    from fleetent.server import _build_platform_maintenance_scheduler

    mock_sched = MagicMock()
    _build_platform_maintenance_scheduler(SchedulingSettings(), _scheduler=mock_sched)

    kw_ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "__kb_connector_sync_sweep__" in kw_ids


def test_sweep_registered_with_60s_default_interval():
    """Sweep must be registered with at least 60 seconds interval by default."""
    from fleetent.config import SchedulingSettings
    from fleetent.server import _build_platform_maintenance_scheduler

    mock_sched = MagicMock()
    _build_platform_maintenance_scheduler(SchedulingSettings(), _scheduler=mock_sched)

    sweep_call = next(
        (
            c
            for c in mock_sched.add_job.call_args_list
            if c.kwargs.get("id") == "__kb_connector_sync_sweep__"
        ),
        None,
    )
    assert sweep_call is not None
    assert sweep_call.kwargs.get("seconds", 0) >= 60


def test_sweep_interval_configurable():
    """Sweep interval must respect kb_connector_sweep_interval_seconds setting."""
    from fleetent.config import SchedulingSettings
    from fleetent.server import _build_platform_maintenance_scheduler

    mock_sched = MagicMock()
    settings = SchedulingSettings(kb_connector_sweep_interval_seconds=300)
    _build_platform_maintenance_scheduler(settings, _scheduler=mock_sched)

    sweep_call = next(
        (
            c
            for c in mock_sched.add_job.call_args_list
            if c.kwargs.get("id") == "__kb_connector_sync_sweep__"
        ),
        None,
    )
    assert sweep_call is not None
    assert sweep_call.kwargs.get("seconds") == 300
