"""KB service config scaffold command."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class InitConfigPlanItem:
    """One planned kb-service init-config filesystem operation."""

    action: str
    path: str


_RESOURCE_DIR = "resources"
_TEMPLATES = (
    ("kb-service.yaml.example", Path("kb-service") / "kb-service.yaml"),
    ("kb-service.env.example", Path("kb-service") / ".env"),
)


def _home_dir() -> Path:
    """Resolve the kb-service home root from process environment."""
    return Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()


def _read_template(template_name: str) -> str:
    resource_root = resources.files("fleetent.knowledge_base").joinpath(_RESOURCE_DIR)
    resource_path = resource_root.joinpath(template_name)
    if resource_path.is_file():
        return resource_path.read_text(encoding="utf-8")
    # Source checkouts read the canonical root examples without depending on cwd.
    project_root = Path(__file__).resolve().parents[3]
    return (project_root / template_name).read_text(encoding="utf-8")


def plan_init_config(home_dir: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Plan kb-service scaffold file operations without mutating the filesystem."""
    plan: list[InitConfigPlanItem] = []
    for _, relative_target in _TEMPLATES:
        target_path = home_dir / relative_target
        action = "create"
        if target_path.exists():
            action = "overwrite" if force else "skip"
        plan.append(InitConfigPlanItem(action=action, path=relative_target.as_posix()))
    return plan


def apply_init_config(home_dir: Path, *, force: bool = False) -> list[InitConfigPlanItem]:
    """Create or update the kb-service scaffold under ``home_dir``."""
    plan = plan_init_config(home_dir, force=force)
    for item, (template_name, relative_target) in zip(plan, _TEMPLATES, strict=True):
        target_path = home_dir / relative_target
        if item.action == "skip":
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_read_template(template_name), encoding="utf-8")
    return plan


def main(argv: list[str] | None = None) -> None:
    """Run ``fleetent kb-service init-config``."""
    parser = argparse.ArgumentParser(prog="fleetent kb-service init-config")
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
    print("next: review kb-service/kb-service.yaml and kb-service/.env before starting KB services")
