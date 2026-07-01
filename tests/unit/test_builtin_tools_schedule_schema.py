"""Schema-level contract for the `schedule` tool: the model receives the tool
schema (not the function docstring body), so the enums and per-parameter
descriptions that steer cron/timezone/task_type MUST live in the schema."""

from __future__ import annotations

from typing import Any

from fleetent.tools import builtin_tools  # noqa: F401 — import registers builtin tools
from fleetent.tools.registry import get_schemas


def _schedule_props() -> dict[str, dict[str, Any]]:
    for schema in get_schemas():
        if schema["function"]["name"] == "schedule":
            return schema["function"]["parameters"]["properties"]
    raise AssertionError("schedule tool not present in get_schemas()")


# ── enums (Literal) ──


def test_schedule_schema_exposes_task_type_enum() -> None:
    assert _schedule_props()["task_type"].get("enum") == ["notify", "generate", "action"]


def test_schedule_schema_exposes_schedule_kind_enum() -> None:
    assert _schedule_props()["schedule_kind"].get("enum") == ["cron", "once", "interval"]


def test_schedule_schema_exposes_action_enum() -> None:
    assert set(_schedule_props()["action"].get("enum") or []) == {
        "create",
        "list",
        "remove",
        "run_now",
        "pause",
        "resume",
        "history",
    }


def test_schedule_schema_exposes_notify_target_type_enum() -> None:
    assert set(_schedule_props()["notify_target_type"].get("enum") or []) == {"user", "channel"}


# ── per-parameter descriptions (Annotated) ──


def test_schedule_timezone_description_warns_against_utc_preconvert() -> None:
    desc = _schedule_props()["timezone"].get("description", "")
    assert "本地" in desc
    assert "UTC" in desc
    assert "默认" in desc


def test_schedule_cron_expr_description_has_local_clock_example() -> None:
    desc = _schedule_props()["cron_expr"].get("description", "")
    assert "本地" in desc
    assert "20" in desc  # the '34 20 * * *' example


def test_schedule_task_type_description_has_selection_rule() -> None:
    desc = _schedule_props()["task_type"].get("description", "")
    assert "notify" in desc
    assert "generate" in desc
    assert "action" in desc
