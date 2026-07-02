#!/usr/bin/env python3
"""Validate a skill repository for CI (frontmatter + safe name + injection audit).

Standalone / vendorable: run as ``python validate_skills.py [repo_root]``. Exits non-zero if
any skill has missing/invalid frontmatter, an unsafe name, or a severe prompt-injection hit.
Injection rules are reused from ``fleetent.skills.audit`` (pure re/dataclass, no third-party
deps) so the CI verdict matches the platform's inbound audit. If fleetent is not installed,
vendor ``audit.py`` next to this script.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from fleetent.skills import audit as skill_audit
except ImportError:  # vendored fallback: audit.py sits next to this script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import audit as skill_audit  # type: ignore[no-redef]

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    if not content.startswith("---"):
        return None, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, content
    if not isinstance(fm, dict):
        return None, content
    return fm, parts[2]


def validate_skill_dir(skill_dir: Path) -> list[str]:
    """Return validation errors for one skill directory (empty list == valid)."""
    errors: list[str] = []
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{name}: missing SKILL.md"]
    content = skill_md.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(content)
    if fm is None:
        errors.append(f"{name}: missing or invalid YAML frontmatter")
        fm = {}
    fm_name = str(fm.get("name") or "")
    if not fm_name:
        errors.append(f"{name}: frontmatter missing 'name'")
    if not str(fm.get("description") or ""):
        errors.append(f"{name}: frontmatter missing 'description'")
    check_name = fm_name or name
    if ".." in check_name or not _SAFE_NAME.match(check_name):
        errors.append(f"{name}: unsafe skill name {check_name!r}")
    hits = skill_audit.audit(body, str(fm.get("description") or ""))
    if skill_audit.has_severe(hits):
        rules = ", ".join(sorted({h.rule_id for h in hits}))
        errors.append(f"{name}: severe prompt-injection ({rules})")
    return errors


def validate_repo(root: Path) -> list[str]:
    """Validate every skill dir (a directory containing SKILL.md) under ``root``."""
    errors: list[str] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        errors.extend(validate_skill_dir(skill_md.parent))
    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path(".")
    errors = validate_repo(root)
    for err in errors:
        print(f"FAIL {err}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} skill validation error(s)", file=sys.stderr)
        return 1
    print("all skills valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
