"""Unit tests: bash_exec description first line declares host worldview (builtin-shell-tool).

schema_builder takes the docstring FIRST line as the tool description; that line must
tell the model bash_exec runs on the host, cannot see /workspace or session files, and
that workspace/session files should be handled via the container exec tool (run_code).
"""

from __future__ import annotations

from fleetent.tools.schema_builder import build_schema
from fleetent.tools.shell_tool import bash_exec


def test_bash_exec_description_is_first_docstring_line() -> None:
    # schema_builder extracts the docstring FIRST line as the description.
    schema = build_schema(bash_exec)
    desc = schema["function"]["description"]
    first_line = (bash_exec.__doc__ or "").strip().splitlines()[0]
    assert desc == first_line
    # Host worldview must live in that single description line.
    assert "run_code" in desc
    assert "/workspace" in desc
    assert ("宿主" in desc) or ("host" in desc.lower())
