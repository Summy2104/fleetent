"""Validate the Slack E2E scenario catalog (slack-e2e-test-suite).

Deterministic gate over tests/e2e/slack_scenarios/*.yaml: structure, unique ids, valid
coverage tags, coverage completeness, and Chinese content. The live LLM-as-user run is
driven separately by the slack-agent-e2e skill; this only checks the catalog is complete
and well-formed.
"""

import re
from pathlib import Path

import pytest
import yaml

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "e2e" / "slack_scenarios"
SAMPLE_AGENT = SCENARIOS_DIR / "agent.yaml.example"

REQUIRED_FIELDS = {"id", "coverage", "persona", "goal", "success_criteria", "max_turns", "channel"}

# Frozen coverage set — every area must have at least one scenario.
COVERAGE_SET = frozenset(
    {
        "chat",
        "memory-in-session",
        "memory-cross-session",
        "clarify",
        "tools",
        "tools-multi",
        "mcp",
        "skills",
        "capability-absent",
        "sandbox",
        "sandbox-error",
        "image",
        "image-text",
        "prompt-injection",
        "long-text",
        "junk-input",
        "thread-continuity",
    }
)

_CJK = re.compile(r"[一-鿿]")


def _has_chinese(text: str) -> bool:
    return bool(_CJK.search(text or ""))


def _load_catalog() -> list[dict]:
    files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    return [yaml.safe_load(f.read_text(encoding="utf-8")) | {"__file__": f.name} for f in files]


def test_catalog_is_non_empty():
    assert SCENARIOS_DIR.is_dir(), f"missing scenarios dir: {SCENARIOS_DIR}"
    assert _load_catalog(), "no scenario files found"


def test_slack_e2e_sample_agent_lives_with_scenarios():
    readme = (SCENARIOS_DIR / "README.md").read_text(encoding="utf-8")

    assert SAMPLE_AGENT.is_file()
    assert "tests/e2e/slack_scenarios/agent.yaml.example" in readme
    assert "config/agents/e2e-tester" not in readme
    assert not Path("config/agents/e2e-tester").exists()


def test_each_scenario_well_formed_and_chinese():
    for case in _load_catalog():
        fname = case["__file__"]
        missing = REQUIRED_FIELDS - case.keys()
        assert not missing, f"{fname}: missing fields {missing}"
        assert isinstance(case["coverage"], list) and case["coverage"], f"{fname}: empty coverage"
        assert isinstance(case["max_turns"], int) and case["max_turns"] > 0, f"{fname}: max_turns"
        for field in ("persona", "goal", "success_criteria"):
            assert _has_chinese(case[field]), f"{fname}: {field} must be non-empty Chinese"


def test_ids_unique():
    ids = [c["id"] for c in _load_catalog()]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate scenario ids: {dupes}"


def test_coverage_tags_valid():
    for case in _load_catalog():
        unknown = set(case["coverage"]) - COVERAGE_SET
        assert not unknown, f"{case['__file__']}: unknown coverage tags {unknown}"


def test_coverage_complete():
    covered: set[str] = set()
    for case in _load_catalog():
        covered.update(case["coverage"])
    missing = COVERAGE_SET - covered
    assert not missing, f"coverage areas with no scenario: {sorted(missing)}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
