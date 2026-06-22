"""Agent-side skill tools: read_skill file_path, list_skills, skill_manage (agent-skill-tools)."""

from __future__ import annotations

from unittest.mock import patch

from fleetent.skills.registry import SkillEntry
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _clean_entry() -> SkillEntry:
    return SkillEntry(description="clean one", path="/y/SKILL.md")


def _blocked_entry() -> SkillEntry:
    return SkillEntry(description="blocked one", path="/x/SKILL.md", audit_blocked=True)


# --- read_skill file_path (skill-read-on-demand) ---


def test_read_skill_with_file_path_returns_support_file() -> None:
    with (
        patch("fleetent.skills.registry._index", {"ok": _clean_entry()}),
        patch(
            "fleetent.skills.registry.read_skill_file", return_value="REF BODY"
        ) as mock_rf,
    ):
        out = builtin_tools.read_skill("ok", file_path="references/api.md")

    assert out == "REF BODY"
    mock_rf.assert_called_once_with("ok", "references/api.md")


def test_read_skill_without_file_path_returns_full_body() -> None:
    with (
        patch("fleetent.skills.registry._index", {"ok": _clean_entry()}),
        patch("fleetent.skills.registry.load", return_value="full body"),
    ):
        out = builtin_tools.read_skill("ok")
    # Unchanged behavior: full SKILL.md + appended guidance.
    assert out.startswith("full body")


def test_read_skill_file_path_blocked_skill_is_refused() -> None:
    with patch("fleetent.skills.registry._index", {"bad": _blocked_entry()}):
        out = builtin_tools.read_skill("bad", file_path="references/api.md")
    assert "blocked" in out.lower()


def test_read_skill_file_path_records_hit() -> None:
    ctx = ToolContext(agent_name="support", session_id="sess-1")
    with (
        patch("fleetent.skills.registry._index", {"ok": _clean_entry()}),
        patch("fleetent.skills.registry.read_skill_file", return_value="REF"),
        patch("fleetent.observability.traces.record_trace_event") as mock_rec,
    ):
        builtin_tools.read_skill("ok", file_path="references/api.md", tool_context=ctx)
    mock_rec.assert_called_once()


# --- list_skills tool (skill-read-on-demand) ---


def test_list_skills_tool_passes_filters_and_returns_json() -> None:
    import json

    with patch(
        "fleetent.skills.registry.query_skills",
        return_value=[{"name": "a", "description": "x"}],
    ) as mock_q:
        out = builtin_tools.list_skills(keyword="kw", category="cat")

    mock_q.assert_called_once_with(keyword="kw", category="cat")
    assert json.loads(out) == [{"name": "a", "description": "x"}]


def test_list_skills_tool_no_args() -> None:
    with patch(
        "fleetent.skills.registry.query_skills", return_value=[]
    ) as mock_q:
        builtin_tools.list_skills()
    mock_q.assert_called_once_with(keyword=None, category=None)


# --- skill_manage tool: approval risk (task 5.1/5.2) ---


def test_skill_manage_registered_at_approval_band() -> None:
    from fleetent.tools import registry as tool_registry

    # medium (or higher) forces the approval gate — agent skill writes are never silent.
    assert tool_registry.get_risk_level("skill_manage") in ("medium", "high")


# --- skill_manage tool: action dispatch (task 5.3/5.4) ---


def test_skill_manage_create_dispatches_with_timestamp() -> None:
    with patch("fleetent.skills.registry.create_skill") as mock_create:
        out = builtin_tools.skill_manage(action="create", name="s", content="BODY")
    assert "ok" in out.lower()
    kwargs = mock_create.call_args.kwargs
    assert mock_create.call_args.args[:2] == ("s", "BODY")
    assert kwargs.get("created_at")  # tool injects a timestamp


def test_skill_manage_edit_patch_delete_dispatch() -> None:
    with (
        patch("fleetent.skills.registry.edit_skill") as me,
        patch("fleetent.skills.registry.patch_skill") as mp,
        patch("fleetent.skills.registry.delete_skill") as md,
        patch("fleetent.skills.registry.write_skill_file") as mw,
        patch("fleetent.skills.registry.remove_skill_file") as mr,
    ):
        builtin_tools.skill_manage(action="edit", name="s", content="B")
        builtin_tools.skill_manage(
            action="patch", name="s", old_string="a", new_string="b"
        )
        builtin_tools.skill_manage(action="delete", name="s")
        builtin_tools.skill_manage(
            action="write_file", name="s", file_path="r/x.md", file_content="C"
        )
        builtin_tools.skill_manage(action="remove_file", name="s", file_path="r/x.md")
    me.assert_called_once()
    mp.assert_called_once()
    md.assert_called_once()
    mw.assert_called_once()
    mr.assert_called_once()


def test_skill_manage_unknown_action_returns_error() -> None:
    out = builtin_tools.skill_manage(action="frobnicate", name="s")
    assert "error" in out.lower()


def test_skill_manage_registry_error_becomes_text() -> None:
    with patch(
        "fleetent.skills.registry.delete_skill",
        side_effect=ValueError("skill 's' is a builtin skill and is read-only"),
    ):
        out = builtin_tools.skill_manage(action="delete", name="s")
    assert "error" in out.lower() and "builtin" in out.lower()


# --- skill_manage tool: observability trace (task 5.5/5.6) ---


def test_skill_manage_success_records_trace() -> None:
    ctx = ToolContext(agent_name="support", session_id="sess-2")
    with (
        patch("fleetent.skills.registry.create_skill"),
        patch("fleetent.observability.traces.record_trace_event") as mock_rec,
    ):
        builtin_tools.skill_manage(
            action="create", name="s", content="B", tool_context=ctx
        )
    mock_rec.assert_called_once()
    event = mock_rec.call_args.args[0]
    assert event.event_type == "skill_authored"
    assert event.payload["skill_name"] == "s"
    assert event.payload["action"] == "create"


def test_skill_manage_failure_records_no_trace() -> None:
    with (
        patch(
            "fleetent.skills.registry.delete_skill", side_effect=ValueError("nope")
        ),
        patch("fleetent.observability.traces.record_trace_event") as mock_rec,
    ):
        builtin_tools.skill_manage(action="delete", name="s")
    mock_rec.assert_not_called()
