"""Unit guards for the renamed tool_auto_approvals store."""

from __future__ import annotations

from pathlib import Path


def test_repo_has_no_legacy_tool_auto_approval_identifier() -> None:
    needle = "approval_" + "allowlist"
    repo_root = Path(__file__).resolve().parents[2]
    checked_roots = [repo_root / "src", repo_root / "tests"]

    offenders: list[str] = []
    for root in checked_roots:
        for path in root.rglob("*"):
            if path.is_dir() or path.suffix not in {".py", ".md"}:
                continue
            rel_path = str(path.relative_to(repo_root))
            if "migration" in rel_path:
                continue
            if needle in rel_path:
                offenders.append(rel_path)
                continue
            if needle in path.read_text():
                offenders.append(rel_path)
    assert offenders == []


def test_tool_auto_approvals_fingerprint_only_matches_same_request() -> None:
    from fleetent.governance.tool_auto_approvals_store import fingerprint

    hit = fingerprint("user:alice", "run_code", {"code": "print(1)", "lang": "py"})
    same = fingerprint("user:alice", "run_code", {"lang": "py", "code": "print(1)"})
    miss = fingerprint("user:alice", "run_code", {"code": "print(2)", "lang": "py"})

    assert hit == same
    assert hit != miss
