from __future__ import annotations

import os
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

        os.utime(path, (timestamp, timestamp))

    plan = plan_diagnostics_retention(
        settings=_settings(tmp_path, logs_days=7, exports_days=7),
        log_dir=log_dir,
        now=now,
    )

    assert old_log in plan.log_files
    assert new_log not in plan.log_files
    assert old_export in plan.diagnostic_exports


def test_retention_plan_defaults_to_root_logs_dir(monkeypatch, tmp_path):
    from fleetent.observability.diagnostics import plan_diagnostics_retention

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    old_root_log = logs_dir / "2026-05-01.log"
    old_root_log.write_text("old")
    legacy_logs_dir = tmp_path / "data" / "logs"
    legacy_logs_dir.mkdir(parents=True)
    legacy_log = legacy_logs_dir / "2026-05-01.log"
    legacy_log.write_text("legacy")
    now = datetime(2026, 6, 2, tzinfo=UTC)
    timestamp = (now - timedelta(days=40)).timestamp()

    os.utime(old_root_log, (timestamp, timestamp))
    os.utime(legacy_log, (timestamp, timestamp))

    plan = plan_diagnostics_retention(
        settings=_settings(tmp_path, enabled=True, logs_days=7),
        now=now,
    )

    assert old_root_log in plan.log_files
    assert legacy_log not in plan.log_files


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


def _patch_traces_db(monkeypatch, tmp_path, rows):
    from pathlib import Path

    from fleetent.db import SQLiteDatabase, create_database
    from fleetent.observability import diagnostics
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate
    from tests.integration.test_migrations import apply_migrations

    db_path = Path(tmp_path) / "traces.db"
    apply_migrations(db_path)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    for ts, run_id in rows:
        database.execute(
            "INSERT INTO traces (id, run_id, event_type, ts, payload_json) "
            "VALUES (:id, :run_id, :event_type, :ts, :payload_json)",
            {
                "id": run_id,
                "run_id": run_id,
                "event_type": "tool_call",
                "ts": ts,
                "payload_json": "{}",
            },
        )
    monkeypatch.setattr(diagnostics, "_database", lambda: database)
    return database


def test_retention_apply_deletes_old_logs_exports_and_traces(monkeypatch, tmp_path):
    from fleetent.observability.diagnostics import apply_diagnostics_retention

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "2026-04-01.log"
    old_log.write_text("old")
    export_dir = tmp_path / "diagnostics"
    export_dir.mkdir()
    old_export = export_dir / "diagnostics-20260401-000000.zip"
    old_export.write_text("zip")
    now = datetime(2026, 6, 2, tzinfo=UTC)
    import os

    stamp = (now - timedelta(days=40)).timestamp()
    for path in (old_log, old_export):
        os.utime(path, (stamp, stamp))

    _patch_traces_db(
        monkeypatch,
        tmp_path,
        rows=[((now - timedelta(days=40)).isoformat(), "old-trace")],
    )

    result = apply_diagnostics_retention(
        settings=_settings(tmp_path, enabled=True, logs_days=7, traces_days=7, exports_days=7),
        log_dir=log_dir,
        now=now,
    )

    assert result.applied is True
    assert result.deleted_logs == 1
    assert result.deleted_exports == 1
    assert result.deleted_traces == 1
    assert result.failures == []
    assert not old_log.exists()
    assert not old_export.exists()


def test_retention_plan_counts_old_traces(monkeypatch, tmp_path):
    from fleetent.observability.diagnostics import plan_diagnostics_retention

    now = datetime(2026, 6, 2, tzinfo=UTC)
    _patch_traces_db(
        monkeypatch,
        tmp_path,
        rows=[
            ((now - timedelta(days=40)).isoformat(), "old-1"),
            (now.isoformat(), "new-1"),
        ],
    )

    plan = plan_diagnostics_retention(
        settings=_settings(tmp_path, enabled=True, traces_days=7),
        now=now,
    )

    assert plan.trace_count == 1


def test_old_trace_count_returns_zero_on_query_error(monkeypatch, tmp_path):
    from fleetent.observability import diagnostics

    class BrokenDatabase:
        def execute(self, *args, **kwargs):
            raise RuntimeError("no table")

    monkeypatch.setattr(diagnostics, "_database", lambda: BrokenDatabase())

    assert diagnostics._old_trace_count(7, datetime(2026, 6, 2, tzinfo=UTC)) == 0


def test_delete_old_traces_returns_zero_when_days_none():
    from fleetent.observability import diagnostics

    assert diagnostics._delete_old_traces(None, datetime(2026, 6, 2, tzinfo=UTC)) == 0


def test_delete_old_traces_returns_zero_on_query_error(monkeypatch):
    from fleetent.observability import diagnostics

    class BrokenDatabase:
        def execute(self, *args, **kwargs):
            raise RuntimeError("locked")

    monkeypatch.setattr(diagnostics, "_database", lambda: BrokenDatabase())

    assert diagnostics._delete_old_traces(7, datetime(2026, 6, 2, tzinfo=UTC)) == 0


def test_delete_files_reports_failures_for_missing_paths(tmp_path):
    from fleetent.observability import diagnostics

    present = tmp_path / "a.zip"
    present.write_text("x")
    missing = tmp_path / "gone.zip"

    deleted, failures = diagnostics._delete_files([present, missing])

    assert deleted == 1
    assert len(failures) == 1
    assert "gone.zip" in failures[0]


def test_database_url_summary_redacts_sqlite_and_keeps_scheme():
    from fleetent.observability import diagnostics

    assert diagnostics._database_url_summary("sqlite:///data/x.db") == "sqlite:///<local-file>"
    assert diagnostics._database_url_summary("postgresql://user:pw@host/db") == "postgresql"


def test_write_logs_returns_empty_when_dir_missing(tmp_path):
    import zipfile

    from fleetent.observability import diagnostics

    archive_path = tmp_path / "out.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        assert diagnostics._write_logs(archive, tmp_path / "absent") == []
