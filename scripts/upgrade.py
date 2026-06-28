from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse

import yaml

from fleetent.config import Settings


def resolve_database_path(database_url: str | None) -> Path:
    effective_url = database_url or os.environ.get("DATABASE_URL") or Settings().database_url
    return sqlite_database_path(effective_url)


def sqlite_database_path(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite" or parsed.netloc:
        raise ValueError("database_url must be a local SQLite URL")

    if database_url.startswith("sqlite:////"):
        raw_path = parsed.path
        if raw_path.startswith("//"):
            raw_path = raw_path[1:]
    elif database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
    else:
        raise ValueError("database_url must be a local SQLite URL")

    if raw_path in {"", ":memory:"}:
        raise ValueError("database_url must be a local SQLite file URL")

    return Path(raw_path)


Warn = Callable[[str], None]


def discover_database_files(data_dir: Path) -> list[Path]:
    """Recursively enumerate every ``*.db`` under *data_dir* (any depth).

    Catch-all discovery (file-system truth) over registry-driven enumeration: it
    covers libraries of stopped/unregistered subjects that a registry walk would miss.
    """
    if not data_dir.exists():
        return []
    return sorted(path for path in data_dir.rglob("*.db") if path.is_file())


def _checkpoint_database(db_path: Path, warn: Warn) -> None:
    """Fold the WAL into the main file via the unified ``db.py`` connection entry.

    Uses ``PRAGMA wal_checkpoint(TRUNCATE)`` so committed but un-checkpointed writes are
    durably in the main file before it is copied. A file that is not a valid SQLite
    database (or is locked) is warned about and left for a raw copy rather than aborting
    the whole backup.
    """
    from fleetent.db import SQLiteDatabase

    try:
        SQLiteDatabase(path=db_path).execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError as exc:
        warn(f"warning: could not checkpoint {db_path}: {exc}")


def _copy_with_sidecars(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    for suffix in _DB_SIDECAR_SUFFIXES:
        sidecar = src.with_name(src.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, dst.with_name(dst.name + suffix))


def _cross_check_registry(data_dir: Path, registry_path: Path | None, warn: Warn) -> None:
    """Warn about subjects the management registry knows but whose directory is absent.

    Best-effort completeness check layered on top of recursive discovery: recursive scan
    is authoritative, the registry only flags gaps (registered-but-missing). Silently
    skipped when the registry is absent or carries no ``tenants`` table (e.g. a fresh or
    standalone deployment).
    """
    if registry_path is None or not registry_path.exists():
        return
    from fleetent.db import ReadOnlySQLiteDatabase

    try:
        rows = ReadOnlySQLiteDatabase(path=registry_path).execute("SELECT id FROM tenants").rows
    except sqlite3.DatabaseError:
        return
    for row in rows:
        tenant_id = row["id"]
        if not (data_dir / str(tenant_id)).exists():
            warn(
                f"warning: registry tenant {tenant_id!r} has no data directory under "
                f"{data_dir}; nothing to back up for it"
            )


def backup_database(
    data_dir: Path,
    backup_root: Path = Path("data/backups"),
    timestamp: datetime | None = None,
    *,
    registry_path: Path | None = None,
    warn: Warn | None = None,
) -> Path:
    """Back up every physical SQLite library under *data_dir* into a timestamped batch.

    Each discovered ``*.db`` is WAL-checkpointed via the ``db.py`` entry, then copied
    (with any ``-wal`` / ``-shm`` sidecars) into ``backup_root/<timestamp>/`` mirroring its
    path relative to *data_dir*. The management registry is cross-checked to surface
    registered-but-missing subjects. Returns the batch directory.
    """
    emit = warn or (lambda _message: None)
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S")
    batch_dir = backup_root / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)
    for db_path in discover_database_files(data_dir):
        _checkpoint_database(db_path, emit)
        _copy_with_sidecars(db_path, batch_dir / db_path.relative_to(data_dir))
    _cross_check_registry(data_dir, registry_path, emit)
    return batch_dir


def restore_database(batch_dir: Path, data_dir: Path) -> list[Path]:
    """Restore every backed-up library from *batch_dir* into *data_dir* (mirrored).

    Symmetric inverse of :func:`backup_database`: each ``*.db`` (plus sidecars) in the
    batch is copied back to its mirrored location under *data_dir*. Use a single backup
    batch so the restored libraries are mutually consistent. Returns the restored paths.
    """
    restored: list[Path] = []
    for db_path in sorted(batch_dir.rglob("*.db")):
        if not db_path.is_file():
            continue
        target = data_dir / db_path.relative_to(batch_dir)
        _copy_with_sidecars(db_path, target)
        restored.append(target)
    return restored


_LEGACY_MANAGEMENT_DB_NAME = "fleetent.db"
_MANAGEMENT_DB_NAME = "management.db"
_DB_SIDECAR_SUFFIXES = ("-wal", "-shm")


def _legacy_rename_candidate(management_path: Path) -> Path | None:
    """Return the legacy ``fleetent.db`` sibling, or None when no rename should apply.

    Only the default ``management.db`` filename participates: a deployment that points
    ``DATABASE_URL`` at a custom filename is never force-renamed (single source of truth
    for that operator's chosen name).
    """
    if management_path.name != _MANAGEMENT_DB_NAME:
        return None
    return management_path.with_name(_LEGACY_MANAGEMENT_DB_NAME)


def rename_legacy_management_db(management_path: Path) -> bool:
    """Rename a legacy ``fleetent.db`` (and its WAL sidecars) to ``management.db``.

    Idempotent compatibility migration for deployments predating the persistence-layer
    #3 management-library rename. Returns True when a rename happened; a no-op (False)
    when ``management.db`` already exists, the filename is customized, or no legacy file
    is present. The ``-wal`` / ``-shm`` sidecars move as a group so SQLite recovery state
    stays intact.
    """
    legacy = _legacy_rename_candidate(management_path)
    if legacy is None or management_path.exists() or not legacy.exists():
        return False
    legacy.rename(management_path)
    for suffix in _DB_SIDECAR_SUFFIXES:
        sidecar = legacy.with_name(legacy.name + suffix)
        if sidecar.exists():
            sidecar.rename(management_path.with_name(management_path.name + suffix))
    return True


def backfill_default_agents(management_path: Path, agents_dir: Path) -> int:
    """Backfill file-based bindings.default flags into agent_admin_state.is_default."""
    from fleetent.db import SQLiteDatabase

    if not agents_dir.exists():
        return 0
    db = SQLiteDatabase(path=management_path)
    updated = 0
    for agent_dir in sorted(p for p in agents_dir.iterdir() if (p / "agent.yaml").is_file()):
        raw = yaml.safe_load((agent_dir / "agent.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            continue
        bindings = raw.get("bindings") or {}
        if not isinstance(bindings, dict) or not bool(bindings.get("default")):
            continue
        name = str(raw.get("name") or agent_dir.name)
        row = db.execute("SELECT id FROM agents WHERE name = :name", {"name": name}).fetchone()
        if row is None:
            continue
        db.execute(
            """
            INSERT INTO agent_admin_state
                (agent_id, status, is_default, archived_at, updated_at)
            VALUES (:agent_id, 'enabled', 1, NULL, :updated_at)
            ON CONFLICT(agent_id) DO UPDATE SET
                is_default = 1,
                updated_at = :updated_at
            """,
            {"agent_id": row["id"], "updated_at": datetime.now().isoformat()},
        )
        updated += 1
    return updated


def run_alembic_upgrade() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", "upgrade", "head"],
        check=False,
        text=True,
        capture_output=True,
    )


def main(
    argv: list[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parser = argparse.ArgumentParser(
        description="Back up local SQLite DB and run Alembic migrations."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--backup-dir", type=Path, default=Path("data/backups"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        database_path = resolve_database_path(args.database_url)
    except ValueError as exc:
        _write(stderr, f"error: {exc}\n")
        return 1

    data_dir = database_path.parent
    legacy_path = _legacy_rename_candidate(database_path)
    legacy_present = legacy_path is not None and legacy_path.exists()

    if not args.dry_run and not database_path.exists() and not legacy_present:
        _write(stderr, f"error: management database file does not exist: {database_path}\n")
        return 1

    if args.dry_run:
        _write(
            stdout,
            f"Would back up all SQLite databases under {data_dir} "
            f"({database_path} and per-tenant/per-agent libraries) to {args.backup_dir}\n",
        )
        if legacy_present:
            _write(stdout, f"Would rename legacy {legacy_path} to {database_path}\n")
        if not args.backup_only:
            _write(stdout, "Would run: alembic upgrade head\n")
        return 0

    # Back up *every* physical library under the data directory before any rename or
    # migration, so the safety snapshot reflects the exact pre-migration state. The
    # management/legacy file doubles as the registry for the cross-check.
    registry_path = database_path if database_path.exists() else legacy_path
    try:
        backup_path = backup_database(
            data_dir,
            args.backup_dir,
            registry_path=registry_path,
            warn=lambda message: _write(stderr, message + "\n"),
        )
    except OSError as exc:
        _write(stderr, f"error: backup failed: {exc}\n")
        return 1

    _write(stdout, f"Backup created: {backup_path}\n")

    # Compatibility rename runs after a successful backup and before Alembic.
    if rename_legacy_management_db(database_path):
        _write(stdout, f"Renamed legacy {legacy_path} to {database_path}\n")

    if args.backup_only:
        return 0

    result = run_alembic_upgrade()
    if result.returncode != 0:
        _write(stderr, result.stderr)
        _write(stderr, f"error: migration failed; backup retained at {backup_path}\n")
        _write(
            stderr,
            "Manual restore: stop service, replace database file from backup, restart service.\n",
        )
        return result.returncode

    _write(stdout, result.stdout)
    agents_dir = Path(os.environ.get("FLEETENT_AGENTS_DIR", str(data_dir.parent / "agents")))
    backfilled = backfill_default_agents(database_path, agents_dir)
    if backfilled:
        _write(stdout, f"Backfilled default-agent flags: {backfilled}\n")
    return 0


def _write(stream: TextIO | None, message: str) -> None:
    if stream is not None:
        stream.write(message)


if __name__ == "__main__":
    raise SystemExit(main())
