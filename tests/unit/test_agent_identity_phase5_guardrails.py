from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def test_observability_agent_side_public_api_uses_agent_name_only_static() -> None:
    root = _repo_root() / "src" / "fleetent" / "observability"
    for rel in ("traces.py", "usage.py", "performance.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "agent_id" not in text, f"{rel} still exposes agent_id in agent-side observability"
