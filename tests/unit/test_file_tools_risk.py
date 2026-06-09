"""Risk-level + tool_context contract for the sandboxed file tools (Task 7).

read/search are structurally safe inside the workspace boundary, so they stay at the
no-approval (LOW) level; write/edit stay at medium. All five tools accept tool_context
so dispatch can key the scope container on the session (same as run_code).
"""

from __future__ import annotations

import fleetent.tools  # noqa: F401  (registers builtin tools as an import side effect)
from fleetent.tools import file_tools
from fleetent.tools.registry import _accepts_tool_context, get_risk_level

_LOW_TOOLS = ["read_file", "search_content", "search_files"]
_MEDIUM_TOOLS = ["write_file", "edit_file"]


def test_read_and_search_are_low_risk() -> None:
    for name in _LOW_TOOLS:
        assert get_risk_level(name) == "none"


def test_write_and_edit_are_medium_risk() -> None:
    for name in _MEDIUM_TOOLS:
        assert get_risk_level(name) == "medium"


def test_all_file_tools_accept_tool_context() -> None:
    for name in _LOW_TOOLS + _MEDIUM_TOOLS:
        fn = getattr(file_tools, name)
        assert _accepts_tool_context(fn), f"{name} must accept tool_context to key its scope"
