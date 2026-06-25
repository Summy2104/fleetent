"""Node config scaffold command."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InitConfigPlanItem:
    """One planned node init-config filesystem operation."""

    action: str
    path: str


_TEMPLATE_NAME = "node.env.example"
_TARGET_PATH = Path("node") / ".env"


def _home_dir() -> Path:
    """Resolve the node home root from process environment."""
    return Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()


def plan_init_config(home_dir: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Plan node scaffold file operations without mutating the filesystem."""
    target_path = home_dir / _TARGET_PATH
    action = "create"
    if target_path.exists():
        action = "overwrite" if force else "skip"
    return [InitConfigPlanItem(action=action, path=_TARGET_PATH.as_posix())]


def apply_init_config(home_dir: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Create or update the node env scaffold under ``home_dir``."""
    plan = plan_init_config(home_dir, force=force)
    target_path = home_dir / _TARGET_PATH
    if not target_path.exists() or force:
        source_path = Path.cwd() / _TEMPLATE_NAME
        if not source_path.exists():
            print(f"missing template: {_TEMPLATE_NAME}", file=sys.stderr)
            raise SystemExit(1)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    return plan


def main(argv: list[str] | None = None) -> None:
    """Run ``fleetent node init-config``."""
    parser = argparse.ArgumentParser(prog="fleetent node init-config")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only")
    parser.add_argument("--force", action="store_true", help="Overwrite generated files")
    args = parser.parse_args(argv)

    home_dir = _home_dir()
    plan = (
        plan_init_config(home_dir, force=args.force)
        if args.dry_run
        else apply_init_config(home_dir, force=args.force)
    )
    for item in plan:
        print(f"{item.action} {item.path}")
    print("next: fill the node service key via node register or dev_node_provision.py")
