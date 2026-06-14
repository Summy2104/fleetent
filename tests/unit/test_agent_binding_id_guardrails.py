"""Guardrails for integer-keyed agent_kbs and agent_skills call sites."""

from __future__ import annotations

import re
from pathlib import Path


def test_no_name_keyed_or_stringified_agent_binding_calls_remain() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    patterns = {
        r"skill_admin_store\.enabled_skill_names\(name\)": "name-keyed enabled_skill_names",
        r"skill_admin_store\.list_skills_for_agent\(name\)": "name-keyed list_skills_for_agent",
        r"skill_admin_store\.set_binding\(name,": "name-keyed set_binding",
        r"skill_admin_store\.has_any_binding\(str\(agent\.id\)\)": "stringified has_any_binding",
        r"skill_admin_store\.enabled_skill_names\(str\(agent\.id\)\)": (
            "stringified enabled_skill_names"
        ),
        r"agent_kbs_store\.list_kbs_for_agent\([^,\n]+,\s*str\(agent\.id\)\)": (
            "stringified list_kbs_for_agent"
        ),
        r"agent_kbs_store\.bind\([^,\n]+,\s*[^,\n]+,\s*str\(agent\.id\)": "stringified bind",
        r"agent_kbs_store\.unbind\([^,\n]+,\s*[^,\n]+,\s*str\(agent\.id\)": "stringified unbind",
    }

    findings: list[str] = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(repo_root)
        for pattern, label in patterns.items():
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line}: {label}")

    assert findings == []
