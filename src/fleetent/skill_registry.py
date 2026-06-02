"""Skill registry: scan skills/, match user input, load SKILL.md content.

``SkillIndex`` encapsulates one skills directory so a per-agent index can be
built without disturbing the global module-level index. The module-level
``scan`` / ``match`` / ``load`` / ``list_skills`` delegate to a shared default
``SkillIndex`` (its index is exposed as ``_index`` for backwards compatibility).
"""

import os
from pathlib import Path

_STOP_WORDS = {"the", "a", "an", "when", "use", "for", "to", "and", "or", "is", "are", "want"}


class SkillIndex:
    """An isolated skill index rooted at a single skills directory."""

    def __init__(self, skills_dir: str | None = None, *, scan: bool = True) -> None:
        # {name: (description, skill_md_path)}
        self._index: dict[str, tuple[str, str]] = {}
        if scan:
            self.scan(skills_dir)

    def scan(self, skills_dir: str | None = None) -> None:
        """Scan the skills directory and build name → (description, path) index."""
        if skills_dir is None:
            skills_dir = os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")
        self._index.clear()
        base = Path(skills_dir)
        if not base.is_dir():
            return
        for skill_md in base.glob("*/SKILL.md"):
            frontmatter = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            name = frontmatter.get("name") or skill_md.parent.name
            description = frontmatter.get("description", "")
            self._index[name] = (description, str(skill_md))

    def match(self, user_input: str) -> str | None:
        """Return the first skill name whose description keywords appear in user_input."""
        lowered = user_input.lower()
        for name, (description, _) in self._index.items():
            keywords = {
                w.strip(".,!?").lower()
                for w in description.split()
                if len(w) > 4 and w.lower() not in _STOP_WORDS
            }
            if any(kw in lowered for kw in keywords):
                return name
        return None

    def load(self, name: str) -> str:
        """Return full SKILL.md content for the named skill."""
        _, path = self._index[name]
        return Path(path).read_text(encoding="utf-8")

    def list_skills(self) -> list[dict[str, str]]:
        """Return all skills as [{"name": ..., "description": ...}]."""
        return [{"name": name, "description": desc} for name, (desc, _) in self._index.items()]


# Shared default index used by the module-level functions. Its backing dict is
# aliased as ``_index`` so existing callers/tests that touch the global keep working.
_DEFAULT = SkillIndex(scan=False)
_index = _DEFAULT._index


def scan(skills_dir: str | None = None) -> None:
    """Scan skills directory and build the global name → (description, path) index."""
    _DEFAULT.scan(skills_dir)


def match(user_input: str) -> str | None:
    """Return the first skill name whose description keywords appear in user_input."""
    return _DEFAULT.match(user_input)


def load(name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    return _DEFAULT.load(name)


def list_skills() -> list[dict[str, str]]:
    """Return all skills as [{"name": ..., "description": ...}]."""
    return _DEFAULT.list_skills()


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract key: value pairs from YAML frontmatter between --- delimiters."""
    result: dict[str, str] = {}
    if not content.startswith("---"):
        return result
    parts = content.split("---", 2)
    if len(parts) < 3:
        return result
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result
