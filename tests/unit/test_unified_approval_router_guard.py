from __future__ import annotations

from pathlib import Path


def test_legacy_resolve_entrypoints_are_only_called_from_router() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    target_calls = {
        "_default_gate.resolve": "permission_gate",
        "reflection_gate.resolve(": "reflection_gate",
    }
    allowed_files = {
        "src/fleetent/governance/approval_router.py",
        "src/fleetent/governance/permission_gate.py",
        "src/fleetent/governance/reflection_gate.py",
        "tests/unit/test_unified_approval_router_guard.py",
    }

    offenders: list[str] = []
    for path in (repo_root / "src").rglob("*.py"):
        rel = str(path.relative_to(repo_root))
        if rel in allowed_files:
            continue
        text = path.read_text()
        if any(needle in text for needle in target_calls):
            offenders.append(rel)
    assert offenders == []
