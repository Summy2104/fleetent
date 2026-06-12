"""Unit: lock the "closed medium → no approval" contract is purely existing.

sandbox-approval-relaxation cashes in免审批 via DEPLOYMENT config + docs only; the
resolver contract MUST NOT change. These tests pin the既有 behavior:
- medium + medium_mode="sandbox" + sandbox_capable → SANDBOX (direct, no approval)
- medium + medium_mode="sandbox" + NOT capable → fail-closed APPROVAL
- high stays APPROVAL under high_mode="approval" (not relaxed alongside medium)
- the risk-constant set (SANDBOX_BACKED_TOOLS) is unchanged
"""

from __future__ import annotations

from fleetent.governance.action_gate import (
    SANDBOX_BACKED_TOOLS,
    ActionMode,
    resolve_action_mode,
)


def _resolve(risk, *, medium="sandbox", high="approval", sandbox_capable=False, force_ask=False):
    return resolve_action_mode(
        risk,
        medium_mode=medium,
        high_mode=high,
        sandbox_capable=sandbox_capable,
        force_ask=force_ask,
    )


def test_closed_medium_sandbox_is_direct_no_approval() -> None:
    assert _resolve("medium", medium="sandbox", sandbox_capable=True) is ActionMode.SANDBOX


def test_unclosed_medium_sandbox_fails_closed_to_approval() -> None:
    assert _resolve("medium", medium="sandbox", sandbox_capable=False) is ActionMode.APPROVAL


def test_high_not_relaxed_with_medium_sandbox() -> None:
    # medium免审批 via sandbox does not touch high — high stays APPROVAL.
    assert (
        _resolve("high", medium="sandbox", high="approval", sandbox_capable=True)
        is ActionMode.APPROVAL
    )


def test_sandbox_backed_tools_constant_unchanged() -> None:
    # Locks the risk-constant set the免审批 cash-in must NOT modify.
    expected = frozenset(
        {"run_code", "read_file", "write_file", "edit_file", "search_content", "search_files"}
    )
    assert expected == SANDBOX_BACKED_TOOLS
