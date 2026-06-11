from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse

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


def backup_database(
    database_path: Path,
    backup_root: Path = Path("data/backups"),
    timestamp: datetime | None = None,
) -> Path:
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / stamp / database_path.name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_path, backup_path)
    return backup_path


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

    legacy_path = _legacy_rename_candidate(database_path)
    legacy_present = legacy_path is not None and legacy_path.exists()

    if not args.dry_run and not database_path.exists() and not legacy_present:
        _write(stderr, f"error: management database file does not exist: {database_path}\n")
        return 1

    if args.dry_run:
        _write(stdout, f"Would back up {database_path} to {args.backup_dir}\n")
        if legacy_present:
            _write(stdout, f"Would rename legacy {legacy_path} to {database_path}\n")
        if not args.backup_only:
            _write(stdout, "Would run: alembic upgrade head\n")
        return 0

    # Back up the live file under its current (possibly legacy) name *before* renaming,
    # so the safety snapshot reflects the exact pre-migration state.
    backup_source = database_path if database_path.exists() else legacy_path
    assert backup_source is not None  # guaranteed by the existence check above
    try:
        backup_path = backup_database(backup_source, args.backup_dir)
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
    return 0


def _write(stream: TextIO | None, message: str) -> None:
    if stream is not None:
        stream.write(message)


if __name__ == "__main__":
    raise SystemExit(main())
