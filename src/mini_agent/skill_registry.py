"""Skill registry: scan skills/, match user input, load SKILL.md content."""

from pathlib import Path

# {name: (description, skill_md_path)}
_index: dict[str, tuple[str, str]] = {}

_STOP_WORDS = {"the", "a", "an", "when", "use", "for", "to", "and", "or", "is", "are", "want"}


def scan(skills_dir: str = "skills") -> None:
    """Scan skills directory and build name → (description, path) index."""
    _index.clear()
    base = Path(skills_dir)
    if not base.is_dir():
        return
    for skill_md in base.glob("*/SKILL.md"):
        frontmatter = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = frontmatter.get("name") or skill_md.parent.name
        description = frontmatter.get("description", "")
        _index[name] = (description, str(skill_md))


def match(user_input: str) -> str | None:
    """Return the first skill name whose description keywords appear in user_input."""
    lowered = user_input.lower()
    for name, (description, _) in _index.items():
        keywords = {
            w.strip(".,!?").lower()
            for w in description.split()
            if len(w) > 4 and w.lower() not in _STOP_WORDS
        }
        if any(kw in lowered for kw in keywords):
            return name
    return None


def load(name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    _, path = _index[name]
    return Path(path).read_text(encoding="utf-8")


def list_skills() -> list[dict[str, str]]:
    """Return all skills as [{"name": ..., "description": ...}]."""
    return [{"name": name, "description": desc} for name, (desc, _) in _index.items()]


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
