"""Skill registry: scan skills/, match user input, load SKILL.md content."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)


@dataclass
class SkillEntry:
    """Indexed metadata for a single skill, parsed from SKILL.md frontmatter."""

    description: str
    path: str
    tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    version: str | None = None
    enabled_by_default: bool = True


_index: dict[str, SkillEntry] = {}

_STOP_WORDS = {"the", "a", "an", "when", "use", "for", "to", "and", "or", "is", "are", "want"}


def scan(skills_dir: str | None = None) -> None:
    """Scan skills directory and build name → SkillEntry index."""
    if skills_dir is None:
        skills_dir = os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")
    _index.clear()
    base = Path(skills_dir)
    if not base.is_dir():
        return
    for skill_md in base.rglob("SKILL.md"):
        frontmatter = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if frontmatter is None:
            logger.warning(
                "skill_frontmatter_parse_failed",
                path=str(skill_md),
                reason="missing --- boundary, invalid YAML, or non-mapping top level",
            )
            continue
        name = frontmatter.get("name") or skill_md.parent.name
        path = str(skill_md)
        existing = _index.get(name)
        if existing is not None:
            # Deterministic selection independent of traversal order: the
            # SKILL.md whose path string sorts first wins; warn on every loser.
            kept_path, dropped_path = sorted((existing.path, path))
            logger.warning(
                "skill_name_conflict",
                name=name,
                kept_path=kept_path,
                dropped_path=dropped_path,
            )
            if existing.path <= path:
                continue
        _index[name] = SkillEntry(
            description=str(frontmatter.get("description", "")),
            path=path,
            tags=_as_str_list(frontmatter.get("tags")),
            platforms=_as_str_list(frontmatter.get("platforms")),
            version=_as_opt_str(frontmatter.get("version")),
            enabled_by_default=bool(frontmatter.get("enabled_by_default", True)),
        )


def match(user_input: str) -> str | None:
    """Return the first skill name whose description keywords appear in user_input."""
    lowered = user_input.lower()
    for name, entry in _index.items():
        keywords = {
            w.strip(".,!?").lower()
            for w in entry.description.split()
            if len(w) > 4 and w.lower() not in _STOP_WORDS
        }
        if any(kw in lowered for kw in keywords):
            return name
    return None


def load(name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    return Path(_index[name].path).read_text(encoding="utf-8")


def list_skills() -> list[dict[str, str]]:
    """Return all skills as [{"name": ..., "description": ...}]."""
    return [{"name": name, "description": entry.description} for name, entry in _index.items()]


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter between leading/trailing --- delimiters.

    Returns the parsed mapping, or None when frontmatter is absent
    (no leading/closing ---), malformed YAML, or not a top-level mapping.
    """
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _as_str_list(value: Any) -> list[str]:
    """Normalize a scalar/list/missing value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_opt_str(value: Any) -> str | None:
    """Normalize a scalar/missing value into an optional string."""
    if value is None:
        return None
    return str(value)
