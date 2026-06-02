from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fleetent.config import DiagnosticsRetentionSettings, DiagnosticsSettings


def _settings(
    tmp_path, *, enabled: bool = True, logs_days=None, traces_days=None, exports_days=None
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


def test_retention_apply_deletes_only_diagnostic_files(tmp_path):
    from fleetent.observability.diagnostics import apply_diagnostics_retention

    now = datetime(2026, 6, 2, tzinfo=UTC)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "2026-05-01.log"
    old_log.write_text("old")
    export_dir = tmp_path / "diagnostics"
    export_dir.mkdir()
    old_export = export_dir / "diagnostics-20260501-000000.zip"
    old_export.write_text("zip")
    data_dir = tmp_path / "data"
    backup_dir = data_dir / "backups" / "20260601-000000"
    backup_dir.mkdir(parents=True)
    backup = backup_dir / "fleetent.db"
    backup.write_text("backup")
    main_db = data_dir / "fleetent.db"
    main_db.write_text("main")
    old_ts = (now - timedelta(days=40)).timestamp()
    import os

    for path in (old_log, old_export):
        os.utime(path, (old_ts, old_ts))

    result = apply_diagnostics_retention(
        settings=_settings(tmp_path, logs_days=7, exports_days=7),
        log_dir=log_dir,
        data_dir=data_dir,
        now=now,
    )

    assert result.applied is True
    assert not old_log.exists()
    assert not old_export.exists()
    assert backup.exists()
    assert main_db.exists()
