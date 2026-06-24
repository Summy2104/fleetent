"""read_skill per-user gating with neutral 'no such skill' message (skill-user-access)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fleetent.skills.registry import SkillEntry
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _entry() -> SkillEntry:
    return SkillEntry(description="secret one", path="/x/SKILL.md")


def _ctx(user_id: str, chat_type: str) -> ToolContext:
    return ToolContext(
        principal=SimpleNamespace(user_id=user_id),
        session_context=SimpleNamespace(chat_type=chat_type),
        skill_user_access={"secret": ["U1"]},
    )


_UNKNOWN = "error: no skill named 'secret'"


def test_unauthorized_dm_gets_neutral_not_found() -> None:
    with patch("fleetent.skills.registry._index", {"secret": _entry()}):
        out = builtin_tools.read_skill("secret", tool_context=_ctx("U9", "dm"))
    assert out == _UNKNOWN  # identical to a genuinely-missing skill — no existence leak


def test_channel_gets_neutral_not_found_even_for_listed_user() -> None:
    with patch("fleetent.skills.registry._index", {"secret": _entry()}):
        out = builtin_tools.read_skill("secret", tool_context=_ctx("U1", "channel"))
    assert out == _UNKNOWN


def test_authorized_dm_loads() -> None:
    with (
        patch("fleetent.skills.registry._index", {"secret": _entry()}),
        patch("fleetent.skills.registry.load", return_value="full body"),
    ):
        out = builtin_tools.read_skill("secret", tool_context=_ctx("U1", "dm"))
    assert out.startswith("full body")


def test_file_path_also_gated() -> None:
    with patch("fleetent.skills.registry._index", {"secret": _entry()}):
        out = builtin_tools.read_skill(
            "secret", file_path="references/x.md", tool_context=_ctx("U9", "dm")
        )
    assert out == _UNKNOWN


def test_public_skill_unaffected() -> None:
    with (
        patch("fleetent.skills.registry._index", {"pub": _entry()}),
        patch("fleetent.skills.registry.load", return_value="pub body"),
    ):
        # 'pub' not in access map => public; any user/chat
        out = builtin_tools.read_skill("pub", tool_context=_ctx("U9", "channel"))
    assert out.startswith("pub body")
