"""Unit tests for the Action Gate risk→mode resolver (action-gate)."""

from __future__ import annotations

from fleetent.governance.action_gate import (
    ActionMode,
    is_sandbox_backed,
    resolve_action_mode,
)


def _resolve(risk, *, medium="approval", high="approval", sandbox_capable=False, force_ask=False):
    return resolve_action_mode(
        risk,
        medium_mode=medium,
        high_mode=high,
        sandbox_capable=sandbox_capable,
        force_ask=force_ask,
    )


# ── basic level → mode ────────────────────────────────────────────────────────


def test_none_is_direct() -> None:
    assert _resolve("none") is ActionMode.DIRECT


def test_low_is_direct() -> None:
    assert _resolve("low") is ActionMode.DIRECT


def test_medium_uses_medium_mode() -> None:
    assert _resolve("medium", medium="approval") is ActionMode.APPROVAL
    assert _resolve("medium", medium="sandbox", sandbox_capable=True) is ActionMode.SANDBOX
    assert _resolve("medium", medium="direct") is ActionMode.DIRECT


def test_high_uses_high_mode() -> None:
    assert _resolve("high", high="approval") is ActionMode.APPROVAL
    assert _resolve("high", high="direct") is ActionMode.DIRECT


# ── CRITICAL is hardcoded reject, unbypassable ────────────────────────────────


def test_critical_is_reject() -> None:
    assert _resolve("critical") is ActionMode.REJECT


def test_critical_reject_ignores_config() -> None:
    assert _resolve("critical", medium="direct", high="direct") is ActionMode.REJECT


def test_critical_reject_ignores_force_ask() -> None:
    assert _resolve("critical", force_ask=True) is ActionMode.REJECT


# ── fail-closed upgrades ──────────────────────────────────────────────────────


def test_unknown_risk_upgrades_to_approval() -> None:
    assert _resolve("totally-unknown") is ActionMode.APPROVAL


def test_sandbox_mode_without_capability_upgrades_to_approval() -> None:
    assert _resolve("medium", medium="sandbox", sandbox_capable=False) is ActionMode.APPROVAL


def test_sandbox_mode_with_capability_stays_sandbox() -> None:
    assert _resolve("medium", medium="sandbox", sandbox_capable=True) is ActionMode.SANDBOX


def test_force_ask_upgrades_non_critical_to_approval() -> None:
    assert _resolve("low", force_ask=True) is ActionMode.APPROVAL
    assert _resolve("medium", medium="direct", force_ask=True) is ActionMode.APPROVAL


# ── sandbox-backed tool registry ──────────────────────────────────────────────


def test_sandbox_backed_tools() -> None:
    backed = ("run_code", "read_file", "write_file", "edit_file", "search_content", "search_files")
    for name in backed:
        assert is_sandbox_backed(name) is True


def test_non_sandbox_backed_tools() -> None:
    for name in ("send_message", "get_current_time", "web_search", "unknown_tool"):
        assert is_sandbox_backed(name) is False
