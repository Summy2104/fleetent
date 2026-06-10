"""Guardrail: identified KB self-connect bypasses must be removed.

bindings.py and operations.py had _database() functions that called
create_database(_settings().database_url) without any injection point.
These bypasses are removed in task 4.2 so that all KB DB access is
routed via TenantRouter rather than reaching the global library.

Other KB files (ingest/runtime.py, management/runtime.py, etc.) have
optional-database fallbacks that are pre-existing technical debt and
tracked separately; they are NOT in scope for this change.
"""

from __future__ import annotations

from pathlib import Path

_KB_ROOT = Path("src/fleetent/knowledge_base")

# Files that must no longer have a create_database(_settings()) call.
_CLEANED_FILES = [
    _KB_ROOT / "bindings.py",
    _KB_ROOT / "operations.py",
]

_SELF_CONNECT_PATTERNS = (
    "create_database(_settings()",
    "create_database(Settings()",
)


def _has_self_connect_pattern(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    return [p for p in _SELF_CONNECT_PATTERNS if p in source]


def test_bindings_has_no_self_connect_bypass() -> None:
    """bindings.py must not call create_database with a settings URL."""
    path = _KB_ROOT / "bindings.py"
    hits = _has_self_connect_pattern(path)
    assert not hits, (
        f"bindings.py still has self-connect bypass: {hits}\n"
        "Remove _database() and route via TenantRouter."
    )


def test_operations_has_no_self_connect_bypass() -> None:
    """operations.py must not call create_database with a settings URL."""
    path = _KB_ROOT / "operations.py"
    hits = _has_self_connect_pattern(path)
    assert not hits, (
        f"operations.py still has self-connect bypass: {hits}\n"
        "Remove _database() and route via TenantRouter."
    )
