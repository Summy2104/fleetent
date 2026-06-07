"""Neutral secret-detection helpers, shared by agent-side config loading and platform
config validation.

Pure functions with no platform/agent coupling and no I/O. Extracted from
platform.config_validation so agent-runtime modules (agent_config, knowledge_base)
can reuse them without importing fleetent.platform (agent/platform decoupling rule).
"""

import re

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"bearer\s+[A-Za-z0-9._-]{10,}|[A-Za-z0-9_-]{24,})",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"(example|placeholder|changeme|replace-me|<.*>|\\$\\{|env:|file://)", re.IGNORECASE
)


def flatten(value: object, prefix: str = "") -> list[tuple[str, object]]:
    """Flatten a nested dict/list config into ``(dotted-key, value)`` pairs."""
    if isinstance(value, dict):
        items: list[tuple[str, object]] = []
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            items.extend(flatten(child, next_prefix))
        return items
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in flatten(child, f"{prefix}.{index}")
        ]
    return [(prefix, value)]


def looks_inline_secret(value: str) -> bool:
    """Whether a string looks like an inline secret (and is not a placeholder/ref)."""
    if not value or _PLACEHOLDER_RE.search(value):
        return False
    return bool(_SECRET_RE.search(value))
