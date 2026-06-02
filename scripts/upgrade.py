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

    if not args.dry_run and not database_path.exists():
        _write(stderr, f"error: database file does not exist: {database_path}\n")
        return 1

    if args.dry_run:
        _write(stdout, f"Would back up {database_path} to {args.backup_dir}\n")
        if not args.backup_only:
            _write(stdout, "Would run: alembic upgrade head\n")
        return 0

    try:
        backup_path = backup_database(database_path, args.backup_dir)
    except OSError as exc:
        _write(stderr, f"error: backup failed: {exc}\n")
        return 1

    _write(stdout, f"Backup created: {backup_path}\n")
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
