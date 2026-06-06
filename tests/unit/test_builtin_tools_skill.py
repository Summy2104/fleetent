"""read_skill audit-refusal logging (skill-read-refusal-audit)."""

from __future__ import annotations

from unittest.mock import patch

from fleetent.skills.registry import SkillEntry
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _blocked_entry() -> SkillEntry:
    return SkillEntry(description="blocked one", path="/x/SKILL.md", audit_blocked=True)


def _clean_entry() -> SkillEntry:
    return SkillEntry(description="clean one", path="/y/SKILL.md")


def test_read_skill_audit_blocked_writes_audit_log() -> None:
    with (
        patch("fleetent.governance.audit_log.write_audit") as mock_audit,
        patch("fleetent.skills.registry._index", {"bad": _blocked_entry()}),
    ):
        out = builtin_tools.read_skill("bad")

    assert "blocked" in out.lower()
    mock_audit.assert_called_once()
    args, kwargs = mock_audit.call_args
    # action is the 2nd positional (actor, action, target_type, target_id, detail)
    assert args[1] == "skill.read_refused"
    assert "bad" in args  # skill name passed as target_id


def test_read_skill_audit_detail_carries_context() -> None:
    ctx = ToolContext(agent_name="support", session_id="sess-1")
    with (
        patch("fleetent.governance.audit_log.write_audit") as mock_audit,
        patch("fleetent.skills.registry._index", {"bad": _blocked_entry()}),
    ):
        builtin_tools.read_skill("bad", tool_context=ctx)

    _, kwargs = mock_audit.call_args
    detail = kwargs.get("detail") or mock_audit.call_args[0][4]
    assert detail["session_id"] == "sess-1"
    assert detail["agent_name"] == "support"
    assert detail["reason"] == "audit_blocked"


def test_read_skill_clean_does_not_write_refusal_audit() -> None:
    with (
        patch("fleetent.governance.audit_log.write_audit") as mock_audit,
        patch("fleetent.skills.registry._index", {"ok": _clean_entry()}),
        patch("fleetent.skills.registry.load", return_value="full body"),
    ):
        out = builtin_tools.read_skill("ok")

    assert out == "full body"
    mock_audit.assert_not_called()


def test_read_skill_refusal_survives_audit_write_failure() -> None:
    with (
        patch(
            "fleetent.governance.audit_log.write_audit", side_effect=RuntimeError("db down")
        ),
        patch("fleetent.skills.registry._index", {"bad": _blocked_entry()}),
    ):
        out = builtin_tools.read_skill("bad")

    # Refusal still returned despite audit failure.
    assert "blocked" in out.lower()
