"""Multi-database backup/restore for the upgrade script (persistence layer #3).

The data directory now holds many physical SQLite libraries under per-subject
subdirectories (``<tenant>/kb.db``, ``<tenant>/shared_memory.db``,
``<tenant>/<agent_id>/agent_state.db`` plus each ``*_vectors.db``). The upgrade
backup must recursively discover and copy *every* library, checkpoint each WAL
before copy so no committed write is lost, mirror the directory structure, and
cross-check the management registry so a registered-but-missing subject is not
silently skipped. Restore is symmetric.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from fleetent.db import ReadOnlySQLiteDatabase, SQLiteDatabase
from scripts import upgrade


def _make_db(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = SQLiteDatabase(path=path)
    db.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    for value in rows:
        db.execute("INSERT INTO t (v) VALUES (:v)", {"v": value})


def _rows(path: Path) -> list[str]:
    db = ReadOnlySQLiteDatabase(path=path)
    return [r["v"] for r in db.execute("SELECT v FROM t ORDER BY v").fetchall()]


def _build_multi_db_data_dir(data_dir: Path) -> list[Path]:
    """Create a representative multi-library layout and return the relative db paths."""
    layout = [
        Path("management.db"),
        Path("tenantA/kb.db"),
        Path("tenantA/kb_vectors.db"),
        Path("tenantA/shared_memory.db"),
        Path("tenantA/shared_memory_vectors.db"),
        Path("tenantA/agent1/agent_state.db"),
        Path("tenantA/agent1/agent_vectors.db"),
    ]
    for rel in layout:
        _make_db(data_dir / rel, [rel.name])
    return layout


def test_backup_mirrors_every_physical_database(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    layout = _build_multi_db_data_dir(data_dir)
    backup_root = tmp_path / "backups"

    batch = upgrade.backup_database(data_dir, backup_root)

    assert batch.parent == backup_root
    for rel in layout:
        copied = batch / rel
        assert copied.exists(), f"missing backup for {rel}"
    # The per-agent state db (in a nested subdirectory) is covered too.
    assert (batch / "tenantA/agent1/agent_state.db").exists()


def test_backup_checkpoints_wal_so_uncheckpointed_writes_are_not_lost(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db_path = data_dir / "tenantA" / "agent1" / "agent_state.db"
    _make_db(db_path, ["committed-and-checkpointed"])
    backup_root = tmp_path / "backups"

    # Park a committed write in the -wal only (autocheckpoint off, connection kept open),
    # so a naive main-file copy would lose it.
    writer = sqlite3.connect(db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO t (v) VALUES ('wal-resident-write')")
        writer.commit()
        assert db_path.with_name(db_path.name + "-wal").exists()

        batch = upgrade.backup_database(data_dir, backup_root)
    finally:
        writer.close()

    # Read the backed-up MAIN file in isolation (drop any copied sidecars): the write must
    # already be in it, which only holds if a checkpoint ran before the copy.
    isolated = tmp_path / "isolated.db"
    shutil.copy2(batch / "tenantA/agent1/agent_state.db", isolated)
    assert "wal-resident-write" in _rows(isolated)


def test_stopped_agent_db_is_discovered_and_missing_registry_subject_warns(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    # A "stopped" agent leaves its state db on disk with no running process.
    stopped = data_dir / "tenantA" / "stopped-agent" / "agent_state.db"
    _make_db(stopped, ["offline-data"])

    # Management registry knows a tenant whose data directory is absent.
    management = data_dir / "management.db"
    mgmt = SQLiteDatabase(path=management)
    mgmt.execute(
        "CREATE TABLE tenants (id TEXT PRIMARY KEY, name TEXT, status TEXT, created_at TEXT)"
    )
    mgmt.execute(
        "INSERT INTO tenants (id, name, status, created_at) VALUES (:id, :name, :status, :ts)",
        {"id": "tenantA", "name": "A", "status": "active", "ts": "2026-06-11"},
    )
    mgmt.execute(
        "INSERT INTO tenants (id, name, status, created_at) VALUES (:id, :name, :status, :ts)",
        {"id": "ghost-tenant", "name": "Ghost", "status": "active", "ts": "2026-06-11"},
    )
    backup_root = tmp_path / "backups"

    warnings: list[str] = []
    batch = upgrade.backup_database(
        data_dir, backup_root, registry_path=management, warn=warnings.append
    )

    # Stopped agent's db was discovered recursively and backed up.
    assert (batch / "tenantA/stopped-agent/agent_state.db").exists()
    # Registered-but-missing subject is surfaced, not silently skipped.
    assert any("ghost-tenant" in w for w in warnings)
    # The present tenant must NOT produce a missing-directory warning.
    assert not any("tenantA" in w for w in warnings)


def test_backup_only_covers_all_databases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    layout = _build_multi_db_data_dir(data_dir)
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(upgrade, "run_alembic_upgrade", lambda: pytest.fail("alembic must not run"))

    exit_code = upgrade.main(
        [
            "--database-url",
            f"sqlite:///{data_dir / 'management.db'}",
            "--backup-dir",
            str(backup_root),
            "--backup-only",
        ]
    )

    assert exit_code == 0
    batches = list(backup_root.iterdir())
    assert len(batches) == 1
    for rel in layout:
        assert (batches[0] / rel).exists(), f"--backup-only missed {rel}"


def test_restore_replaces_all_databases_including_subdirectories(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    layout = _build_multi_db_data_dir(data_dir)
    backup_root = tmp_path / "backups"

    batch = upgrade.backup_database(data_dir, backup_root)

    # Simulate a botched migration: wipe the live data directory entirely.
    shutil.rmtree(data_dir)
    assert not data_dir.exists()

    restored = upgrade.restore_database(batch, data_dir)

    assert {p.relative_to(data_dir) for p in restored} == set(layout)
    for rel in layout:
        target = data_dir / rel
        assert target.exists()
        assert _rows(target) == [rel.name]
