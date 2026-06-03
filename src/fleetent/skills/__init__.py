"""Skills capability public API.

Scan the builtin + user `skills/` directories, keyword-match user input against
SKILL.md frontmatter, render the read-on-demand catalog, and gate skills through
the static injection audit. Cross-package callers import from here (or
``from fleetent.skills import registry as skill_registry``), not from the
internal modules. ``audit`` stays package-internal — only ``registry``
references it (via ``from fleetent.skills import audit``); its symbols are not
re-exported here because the ``audit`` name would shadow the submodule.
"""

from fleetent.skills.registry import (
    BUILTIN_SKILLS_DIR,
    SkillEntry,
    SkillIndex,
    available_skills_prompt,
    collect_disabled_trace,
    list_skills,
    load,
    load_errors,
    match,
    reload,
    scan,
)

__all__ = [
    "BUILTIN_SKILLS_DIR",
    "SkillEntry",
    "SkillIndex",
    "available_skills_prompt",
    "collect_disabled_trace",
    "list_skills",
    "load",
    "load_errors",
    "match",
    "reload",
    "scan",
]
