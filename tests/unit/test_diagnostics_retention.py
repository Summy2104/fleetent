from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fleetent.config import DiagnosticsRetentionSettings, DiagnosticsSettings


def _settings(
    tmp_path, *, enabled: bool = False, logs_days=None, traces_days=None, exports_days=None
):
    return DiagnosticsSettings(
        export_dir=str(tmp_path / "diagnostics"),
        retention=DiagnosticsRetentionSettings(
            enabled=enabled,
            logs_days=logs_days,
            traces_days=traces_days,
            diagnostic_exports_days=exports_days,
        ),
    )


def test_retention_plan_identifies_old_logs_and_exports(tmp_path):
    from fleetent.observability.diagnostics import plan_diagnostics_retention

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "2026-05-01.log"
    new_log = log_dir / "2026-06-02.log"
    old_log.write_text("old")
    new_log.write_text("new")
    export_dir = tmp_path / "diagnostics"
    export_dir.mkdir()
    old_export = export_dir / "diagnostics-20260501-000000.zip"
    old_export.write_text("zip")
    now = datetime(2026, 6, 2, tzinfo=UTC)
    for path in (old_log, old_export):
        timestamp = (now - timedelta(days=40)).timestamp()
        path.touch()
        import os

        os.utime(path, (timestamp, timestamp))

    plan = plan_diagnostics_retention(
        settings=_settings(tmp_path, logs_days=7, exports_days=7),
        log_dir=log_dir,
        now=now,
    )

    assert old_log in plan.log_files
    assert new_log not in plan.log_files
    assert old_export in plan.diagnostic_exports


def test_retention_days_none_produces_no_candidates(tmp_path):
    from fleetent.observability.diagnostics import plan_diagnostics_retention

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "2026-05-01.log"
    old_log.write_text("old")

    plan = plan_diagnostics_retention(
        settings=_settings(tmp_path, enabled=True),
        log_dir=log_dir,
        now=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert plan.log_files == []
    assert plan.trace_count == 0
    assert plan.diagnostic_exports == []


def test_retention_apply_disabled_fails_fast(tmp_path):
    from fleetent.observability.diagnostics import apply_diagnostics_retention

    result = apply_diagnostics_retention(settings=_settings(tmp_path, enabled=False, logs_days=1))

    assert result.applied is False
    assert "disabled" in result.message
