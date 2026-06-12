"""Integration: bash_exec opt-in across schema visibility and dispatch.

A normal agent (`allowed_tools: []` → allow-all → None) does not see or dispatch
`bash_exec`; an ops agent that explicitly names it does. Exercises the real tool
registry (import side-effect registration), the production schema filter
(`filter_tool_schemas`), and `dispatch` so the two surfaces stay consistent.
"""

from __future__ import annotations

import pytest

import fleetent.runtime.snapshot as agent_runtime
import fleetent.tools  # noqa: F401 — import side-effect registers builtin tools
from fleetent.tools.registry import dispatch, get_schemas


def _visible(allowed_tools):
    schemas = get_schemas()
    return {
        s["function"]["name"]
        for s in agent_runtime.filter_tool_schemas(schemas, allowed_tools, None)
    }


def test_bash_exec_registered() -> None:
    assert "bash_exec" in {s["function"]["name"] for s in get_schemas()}


def test_normal_agent_allow_all_schema_excludes_bash_exec() -> None:
    visible = _visible(None)
    assert "bash_exec" not in visible
    # Non-opt-in builtins remain visible under allow-all.
    assert "run_code" in visible


def test_ops_agent_explicit_schema_includes_bash_exec() -> None:
    assert "bash_exec" in _visible(["bash_exec"])


def test_dispatch_bash_exec_rejected_under_allow_all() -> None:
    with pytest.raises(PermissionError):
        dispatch("bash_exec", "{}", allowed_tools=None)


def test_dispatch_bash_exec_allowed_when_explicit() -> None:
    # Explicit grant passes the policy check; we stop before execution by passing a
    # no-op command, but the point is no PermissionError is raised by the policy.
    result = dispatch(
        "bash_exec",
        '{"command": "true", "description": "noop"}',
        allowed_tools=["bash_exec"],
    )
    # dispatch returns a coroutine for async tools; awaiting is not needed to prove
    # the policy gate passed (no PermissionError). Close it to avoid a warning.
    if hasattr(result, "close"):
        result.close()
