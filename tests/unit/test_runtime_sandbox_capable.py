"""Unit tests for runtime containment gating (sandbox-containment-gating).

`runtime_sandbox_capable` decides the `sandbox_capable` truth fed to the action
gate from *runtime* containment, not a static tool-name lookup: a tool is capable
only when it is sandbox-backed AND the effective mode is not OFF AND the tool
actually executes inside the container this call (workspace mount available for file
tools; run_code execs in-container whenever mode != OFF).
"""

from __future__ import annotations

from fleetent.integrations.sandbox import Mode
from fleetent.runtime.loop import runtime_sandbox_capable


def test_non_sandbox_backed_tool_never_capable():
    assert runtime_sandbox_capable("send_email", Mode.ALL, workspace_mount=True) is False


def test_mode_off_makes_capable_false():
    """OFF means no box at all — even a sandbox-backed tool is not capable."""
    assert runtime_sandbox_capable("run_code", Mode.OFF, workspace_mount=True) is False
    assert runtime_sandbox_capable("write_file", Mode.OFF, workspace_mount=True) is False


def test_none_mode_makes_capable_false():
    """A caller without a resolved mode is treated as not-contained (fail closed)."""
    assert runtime_sandbox_capable("run_code", None, workspace_mount=True) is False


def test_file_tool_requires_workspace_mount():
    """File tools degrade to the host fence without workspace_mount → not capable."""
    assert runtime_sandbox_capable("write_file", Mode.ALL, workspace_mount=False) is False
    assert runtime_sandbox_capable("read_file", Mode.ALL, workspace_mount=False) is False


def test_file_tool_capable_when_contained():
    assert runtime_sandbox_capable("write_file", Mode.ALL, workspace_mount=True) is True
    assert runtime_sandbox_capable("edit_file", Mode.SELECTIVE, workspace_mount=True) is True


def test_run_code_capable_without_mount_when_mode_on():
    """run_code execs inside the container regardless of host bind-mount, so a
    mount-less backend (e.g. microsandbox) still contains it when mode != OFF."""
    assert runtime_sandbox_capable("run_code", Mode.ALL, workspace_mount=False) is True
