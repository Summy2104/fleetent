"""Platform upgrade command — delegates to scripts/upgrade.py logic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO


def _upgrade_main(
    argv: list[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    from scripts.upgrade import main as scripts_upgrade_main

    return scripts_upgrade_main(argv=argv, stdout=stdout, stderr=stderr)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the upgrade subcommand."""
    parser = subparsers.add_parser(
        "upgrade",
        help="Back up SQLite databases and run Alembic migrations",
    )
    parser.add_argument("--database-url", help="Override the management database URL")
    parser.add_argument(
        "--backup-dir", default=None, help="Root directory for backup batches (default: data/backups)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned operations; do nothing")
    parser.add_argument("--backup-only", action="store_true", help="Back up only; skip Alembic")


def handle(args: argparse.Namespace) -> bool:
    """Handle the upgrade subcommand."""
    if args.cmd != "upgrade":
        return False

    argv: list[str] = []
    if args.database_url:
        argv += ["--database-url", args.database_url]
    if args.backup_dir:
        argv += ["--backup-dir", str(args.backup_dir)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.backup_only:
        argv.append("--backup-only")

    exit_code = _upgrade_main(argv=argv, stdout=sys.stdout, stderr=sys.stderr)
    if exit_code:
        sys.exit(exit_code)
    return True
