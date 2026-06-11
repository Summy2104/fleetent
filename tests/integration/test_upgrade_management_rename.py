"""Upgrade-time legacy management DB rename: fleetent.db -> management.db.

Persistence layer #3 renamed the management library file. Existing deployments
still carry data/fleetent.db; the upgrade script renames it (with its WAL
sidecars) to management.db after backup and before running Alembic, idempotently
and only for the default filename.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase
from scripts import upgrade


def _fake_alembic_capturing(state: dict[str, object], data_dir: Path, backup_root: Path):
    legacy = data_dir / "fleetent.db"
    management = data_dir / "management.db"

    def _run() -> CompletedProcess[str]:
        state["management_exists_at_migrate"] = management.exists()
        state["legacy_gone_at_migrate"] = not legacy.exists()
        state["backup_has_legacy_at_migrate"] = bool(list(backup_root.glob("*/fleetent.db")))
        return CompletedProcess(["alembic", "upgrade", "head"], 0, stdout="ok\n", stderr="")

    return _run


def test_legacy_fleetent_db_renamed_to_management_db_after_backup_before_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy = data_dir / "fleetent.db"
    # A real SQLite management library predating the rename.
    legacy_db = SQLiteDatabase(path=legacy)
    legacy_db.execute("CREATE TABLE marker (v TEXT)")
    legacy_db.execute("INSERT INTO marker (v) VALUES ('legacy-row')")
    backup_root = tmp_path / "backups"

    state: dict[str, object] = {}
    monkeypatch.setattr(
        upgrade, "run_alembic_upgrade", _fake_alembic_capturing(state, data_dir, backup_root)
    )

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{data_dir / 'management.db'}",
            "--backup-dir",
            str(backup_root),
        ]
    )

    assert exit_code == 0
    # The renamed management.db is a valid SQLite library carrying the original data.
    management = data_dir / "management.db"
    assert management.exists()
    rows = ReadOnlySQLiteDatabase(path=management).execute("SELECT v FROM marker").fetchall()
    assert [r["v"] for r in rows] == ["legacy-row"]
    assert not legacy.exists()
    assert not (data_dir / "fleetent.db-wal").exists()
    assert not (data_dir / "fleetent.db-shm").exists()
    # Rename happened before migrate (management present, legacy gone at alembic time).
    assert state["management_exists_at_migrate"] is True
    assert state["legacy_gone_at_migrate"] is True
    # Backup was taken before the rename (it captured the pre-rename legacy name).
    assert state["backup_has_legacy_at_migrate"] is True


def test_rename_is_idempotent_when_management_db_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    management = data_dir / "management.db"
    management.write_bytes(b"current management db")
    # A stray legacy file must NOT clobber the live management.db.
    legacy = data_dir / "fleetent.db"
    legacy.write_bytes(b"stale legacy db")
    backup_root = tmp_path / "backups"

    monkeypatch.setattr(
        upgrade,
        "run_alembic_upgrade",
        lambda: CompletedProcess(["alembic", "upgrade", "head"], 0, stdout="ok\n", stderr=""),
    )

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{management}",
            "--backup-dir",
            str(backup_root),
        ]
    )

    assert exit_code == 0
    # No rename: management.db untouched, legacy left in place.
    assert management.read_bytes() == b"current management db"
    assert legacy.exists()


def test_custom_database_url_filename_is_not_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    custom = data_dir / "custom.db"
    custom.write_bytes(b"custom db")
    # A legacy fleetent.db sibling must be ignored when the configured filename is custom.
    legacy = data_dir / "fleetent.db"
    legacy.write_bytes(b"legacy db")
    backup_root = tmp_path / "backups"

    monkeypatch.setattr(
        upgrade,
        "run_alembic_upgrade",
        lambda: CompletedProcess(["alembic", "upgrade", "head"], 0, stdout="ok\n", stderr=""),
    )

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{custom}",
            "--backup-dir",
            str(backup_root),
        ]
    )

    assert exit_code == 0
    assert custom.read_bytes() == b"custom db"
    assert legacy.read_bytes() == b"legacy db"
    assert not (data_dir / "management.db").exists()


def test_rename_function_renames_main_and_sidecars(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "fleetent.db").write_bytes(b"main")
    (data_dir / "fleetent.db-wal").write_bytes(b"wal")
    (data_dir / "fleetent.db-shm").write_bytes(b"shm")

    renamed = upgrade.rename_legacy_management_db(data_dir / "management.db")

    assert renamed is True
    assert (data_dir / "management.db").read_bytes() == b"main"
    assert (data_dir / "management.db-wal").read_bytes() == b"wal"
    assert (data_dir / "management.db-shm").read_bytes() == b"shm"


def test_rename_function_noop_without_legacy(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    assert upgrade.rename_legacy_management_db(data_dir / "management.db") is False
