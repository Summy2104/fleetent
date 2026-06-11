from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts import upgrade


class FakeSettings:
    def __init__(self, database_url: str = "sqlite:///data/fleetent.db") -> None:
        self.database_url = database_url


def test_database_url_cli_argument_takes_precedence_over_env_and_settings(monkeypatch, tmp_path):
    cli_db = tmp_path / "cli.db"
    env_db = tmp_path / "env.db"
    settings_db = tmp_path / "settings.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{env_db}")
    monkeypatch.setattr(upgrade, "Settings", lambda: FakeSettings(f"sqlite:///{settings_db}"))

    resolved = upgrade.resolve_database_path(f"sqlite:///{cli_db}")

    assert resolved == cli_db


def test_database_url_env_takes_precedence_over_settings(monkeypatch, tmp_path):
    env_db = tmp_path / "env.db"
    settings_db = tmp_path / "settings.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{env_db}")
    monkeypatch.setattr(upgrade, "Settings", lambda: FakeSettings(f"sqlite:///{settings_db}"))

    resolved = upgrade.resolve_database_path(None)

    assert resolved == env_db


def test_database_url_falls_back_to_settings(monkeypatch, tmp_path):
    settings_db = tmp_path / "settings.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(upgrade, "Settings", lambda: FakeSettings(f"sqlite:///{settings_db}"))

    resolved = upgrade.resolve_database_path(None)

    assert resolved == settings_db


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://db.example/fleetent",
        "sqlite://remote.example/fleetent.db",
        "sqlite:///:memory:",
    ],
)
def test_unsupported_database_url_fails_fast_without_creating_backup(
    monkeypatch, tmp_path, database_url
):
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic called"))

    exit_code = upgrade.main(
        ["--database-url", database_url, "--backup-dir", str(backup_root)],
        stdout=None,
        stderr=None,
    )

    assert exit_code != 0
    assert not backup_root.exists()


def test_missing_database_file_fails_fast_without_running_migration(monkeypatch, tmp_path, capsys):
    missing_db = tmp_path / "missing.db"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic called"))

    exit_code = upgrade.main(
        ["--database-url", f"sqlite:///{missing_db}", "--backup-dir", str(backup_root)],
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "database file does not exist" in captured.err
    assert not backup_root.exists()


def test_default_backup_path_uses_timestamped_data_backups_directory(monkeypatch, tmp_path):
    # backup_database now operates on the whole data directory and mirrors structure;
    # the multi-database behaviour (recursive discovery, WAL checkpoint, registry
    # cross-check, restore) is covered by tests/integration/test_upgrade_multi_db_backup.py.
    monkeypatch.chdir(tmp_path)
    data_dir = Path("data")
    data_dir.mkdir()

    batch_dir = upgrade.backup_database(
        data_dir,
        timestamp=datetime(2026, 6, 1, 12, 34, 56),
    )

    assert batch_dir == Path("data/backups/20260601-123456")
    assert batch_dir.is_dir()


def test_backup_dir_argument_overrides_default_backup_root(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    backup_root = tmp_path / "custom-backups"

    batch_dir = upgrade.backup_database(
        data_dir,
        backup_root,
        timestamp=datetime(2026, 6, 1, 12, 34, 56),
    )

    assert batch_dir == backup_root / "20260601-123456"


def test_backup_creates_missing_backup_directory(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    backup_root = tmp_path / "missing" / "backups"

    batch_dir = upgrade.backup_database(
        data_dir,
        backup_root,
        timestamp=datetime(2026, 6, 1, 12, 34, 56),
    )

    assert batch_dir.exists()


def test_dry_run_outputs_plan_without_requiring_database_file_or_running_alembic(
    monkeypatch, tmp_path, capsys
):
    missing_db = tmp_path / "missing.db"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic called"))

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{missing_db}",
            "--backup-dir",
            str(backup_root),
            "--dry-run",
        ],
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(missing_db) in captured.out
    assert str(backup_root) in captured.out
    assert "alembic upgrade head" in captured.out
    assert not backup_root.exists()


def test_backup_only_creates_backup_without_running_alembic(monkeypatch, tmp_path):
    database_path = tmp_path / "fleetent.db"
    database_path.write_bytes(b"source database")
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic called"))

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{database_path}",
            "--backup-dir",
            str(backup_root),
            "--backup-only",
        ],
    )

    assert exit_code == 0
    backups = list(backup_root.glob("*/fleetent.db"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"source database"


def test_default_upgrade_runs_alembic_after_backup(monkeypatch, tmp_path):
    database_path = tmp_path / "fleetent.db"
    database_path.write_bytes(b"source database")
    backup_root = tmp_path / "backups"
    events = []

    def fake_run_alembic_upgrade():
        events.append(("alembic", list(backup_root.glob("*/fleetent.db"))))
        return CompletedProcess(["alembic", "upgrade", "head"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(upgrade, "run_alembic_upgrade", fake_run_alembic_upgrade)

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{database_path}",
            "--backup-dir",
            str(backup_root),
        ],
    )

    assert exit_code == 0
    assert len(events) == 1
    assert len(events[0][1]) == 1


def test_backup_failure_prevents_alembic_and_returns_non_zero(monkeypatch, tmp_path):
    database_path = tmp_path / "fleetent.db"
    database_path.write_bytes(b"source database")
    monkeypatch.setattr(
        upgrade,
        "backup_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic called"))

    exit_code = upgrade.main(["--database-url", f"sqlite:///{database_path}"])

    assert exit_code != 0


def test_alembic_failure_keeps_backup_and_prints_manual_restore_hint(monkeypatch, tmp_path, capsys):
    database_path = tmp_path / "fleetent.db"
    database_path.write_bytes(b"source database")
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(
        upgrade,
        "run_alembic_upgrade",
        lambda: CompletedProcess(
            ["alembic", "upgrade", "head"],
            2,
            stdout="",
            stderr="migration error\n",
        ),
    )

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{database_path}",
            "--backup-dir",
            str(backup_root),
        ],
    )

    captured = capsys.readouterr()
    backups = list(backup_root.glob("*/fleetent.db"))
    assert exit_code != 0
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"source database"
    assert "Manual restore" in captured.err
    assert "stop service" in captured.err
