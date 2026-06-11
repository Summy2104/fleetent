"""Integration: runtime containment gating composed with the real action gate.

Exercises the actual `runtime_sandbox_capable` (runtime) feeding the real
`resolve_action_mode` (governance) across mode/mount combinations — no mocks — so
the two modules' contract holds together: an uncontained run (effective mode OFF, or
a mount-less backend for file tools) escalates a `sandbox`-configured medium op to
APPROVAL, while a contained run runs it as SANDBOX directly.
"""

from __future__ import annotations

from fleetent.governance.action_gate import ActionMode, resolve_action_mode
from fleetent.integrations.sandbox import Mode
from fleetent.runtime.loop import runtime_sandbox_capable


def _gate(tool: str, mode: Mode | None, *, workspace_mount: bool) -> ActionMode:
    return resolve_action_mode(
        "medium",
        medium_mode="sandbox",
        high_mode="approval",
        sandbox_capable=runtime_sandbox_capable(tool, mode, workspace_mount=workspace_mount),
        force_ask=False,
    )


def test_off_mode_escalates_sandbox_op_to_approval() -> None:
    """effective_mode OFF (no docker) → the sandbox-configured op fails closed."""
    assert _gate("run_code", Mode.OFF, workspace_mount=True) is ActionMode.APPROVAL
    assert _gate("write_file", Mode.OFF, workspace_mount=True) is ActionMode.APPROVAL


def test_contained_run_runs_sandbox_directly() -> None:
    """Contained run (mode on + run_code in-container) → SANDBOX, no approval."""
    assert _gate("run_code", Mode.ALL, workspace_mount=True) is ActionMode.SANDBOX


def test_file_tool_no_mount_backend_escalates() -> None:
    """A mount-less backend (e.g. microsandbox) degrades file tools to the host
    fence — they are not contained, so a `sandbox` file op escalates to APPROVAL."""
    assert _gate("write_file", Mode.ALL, workspace_mount=False) is ActionMode.APPROVAL


def test_run_code_no_mount_backend_still_sandbox() -> None:
    """run_code execs in-container even on a mount-less backend → still SANDBOX."""
    assert _gate("run_code", Mode.ALL, workspace_mount=False) is ActionMode.SANDBOX
