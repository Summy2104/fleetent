"""Deployment configuration initialization command."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InitConfigPlanItem:
    """A planned init-config filesystem operation."""

    action: str
    path: str


_GENERATED_FILES = (
    (".env.example", ".env"),
    ("platform.yaml.example", "platform.yaml"),
)
_GENERATED_DIRS = (
    "data/",
    "data/logs/",
    "data/diagnostics/",
    "secrets/",
)


def _display_path(path: str, *, directory: bool = False) -> str:
    return f"{path}/" if directory and not path.endswith("/") else path


def plan_init_config(root: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Return init-config operations for a deployment root."""
    items: list[InitConfigPlanItem] = []
    for _, target in _GENERATED_FILES:
        action = "create"
        if (root / target).exists():
            action = "overwrite" if force else "skip"
        items.append(InitConfigPlanItem(action, target))

    for directory in _GENERATED_DIRS:
        normalized = directory.rstrip("/")
        action = "skip" if (root / normalized).exists() else "create"
        items.append(InitConfigPlanItem(action, _display_path(normalized, directory=True)))
    return items


def apply_init_config(root: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Create local deployment config files and directories."""
    plan = plan_init_config(root, force=force)
    for source, target in _GENERATED_FILES:
        target_path = root / target
        if target_path.exists() and not force:
            continue
        source_path = root / source
        if not source_path.exists():
            print(f"missing template: {source}", file=sys.stderr)
            sys.exit(1)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    for directory in _GENERATED_DIRS:
        (root / directory.rstrip("/")).mkdir(parents=True, exist_ok=True)
    return plan


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register deployment config initialization command."""
    parser = subparsers.add_parser("init-config", help="Initialize local deployment config")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only")
    parser.add_argument("--force", action="store_true", help="Overwrite generated files")


def handle(args: argparse.Namespace) -> bool:
    """Handle deployment config initialization command."""
    if args.cmd != "init-config":
        return False

    if args.dry_run:
        plan = plan_init_config(Path.cwd(), force=args.force)
    else:
        plan = apply_init_config(Path.cwd(), force=args.force)

    for item in plan:
        print(f"{item.action} {item.path}")
    print("next: edit .env and platform.yaml, then place real secret files in secrets/")
    return True
