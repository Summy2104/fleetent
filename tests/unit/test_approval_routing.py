"""Unit tests for approval route resolution (A2 task 2.3/2.4).

Tests resolve_approvers(): by_tool overrides by_risk, opaque address parsing,
and empty-result → default-closed trigger.
"""

from __future__ import annotations


def _routing(**kwargs):  # type: ignore[no-untyped-def]
    from fleetent.agent_config import ApprovalRouting

    return ApprovalRouting(**kwargs)


# ── by_tool overrides by_risk ─────────────────────────────────────────────────


def test_by_tool_overrides_by_risk_for_matching_tool() -> None:
    """When by_tool has an entry for the tool, it supersedes by_risk."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"high": {"approvers": ["slack:U_RISK"], "policy": "any"}},
        by_tool={"delete_db": {"approvers": ["slack:U_OPS"], "policy": "all"}},
    )

    addrs, policy = resolve_approvers(routing, risk_level="high", tool_name="delete_db")

    assert addrs == [("slack", "U_OPS")]
    assert policy == "all"


def test_by_risk_used_when_tool_not_in_by_tool() -> None:
    """When by_tool has no entry for the tool, fall back to by_risk."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}},
        by_tool={"other_tool": {"approvers": ["slack:U_OTHER"], "policy": "any"}},
    )

    addrs, policy = resolve_approvers(routing, risk_level="high", tool_name="write_file")

    assert addrs == [("slack", "U_LEAD")]
    assert policy == "any"


# ── address parsing (opaque platform:target_id format) ────────────────────────


def test_approver_parsed_into_platform_target_tuple() -> None:
    """Opaque 'platform:target_id' strings are parsed into (platform, target_id) tuples."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={
            "medium": {
                "approvers": ["slack:U123456", "telegram:987654321"],
                "policy": "any",
            }
        }
    )

    addrs, policy = resolve_approvers(routing, risk_level="medium", tool_name="run_code")

    assert ("slack", "U123456") in addrs
    assert ("telegram", "987654321") in addrs
    assert policy == "any"


def test_malformed_approver_address_excluded() -> None:
    """Approver strings without ':' are excluded from the resolved list."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={
            "high": {
                "approvers": ["slack:U_GOOD", "MALFORMED_NO_COLON"],
                "policy": "any",
            }
        }
    )

    addrs, _ = resolve_approvers(routing, risk_level="high", tool_name="any_tool")

    platforms = [p for p, _ in addrs]
    assert "MALFORMED_NO_COLON" not in platforms
    assert ("slack", "U_GOOD") in addrs


# ── empty result → default-closed ─────────────────────────────────────────────


def test_no_entry_for_risk_returns_empty_list() -> None:
    """No by_risk entry for the given risk level → empty list → default-closed."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}},
    )

    addrs, _ = resolve_approvers(routing, risk_level="medium", tool_name="run_code")

    assert addrs == []


def test_empty_approvers_list_returns_empty() -> None:
    """An entry with an empty approvers list resolves to empty → default-closed."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"high": {"approvers": [], "policy": "any"}},
    )

    addrs, _ = resolve_approvers(routing, risk_level="high", tool_name="any_tool")

    assert addrs == []


# ── requester sentinel ────────────────────────────────────────────────────────


def test_requester_sentinel_resolved_as_requester_address() -> None:
    """The literal 'requester' entry resolves to the ('requester', '') sentinel tuple."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"medium": {"approvers": ["requester"], "policy": "any"}},
    )

    addrs, _ = resolve_approvers(routing, risk_level="medium", tool_name="send_im_message")

    assert addrs == [("requester", "")]


def test_requester_sentinel_mixes_with_outbound_addresses() -> None:
    """Sentinel and platform:target addresses coexist in one resolved list."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"medium": {"approvers": ["requester", "slack:U_ADMIN"], "policy": "any"}},
    )

    addrs, _ = resolve_approvers(routing, risk_level="medium", tool_name="any_tool")

    assert ("requester", "") in addrs
    assert ("slack", "U_ADMIN") in addrs


def test_requester_with_target_is_reserved_and_skipped() -> None:
    """'requester:<anything>' is reserved namespace — skipped, never an outbound address."""
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"medium": {"approvers": ["requester:U_SPOOF", "slack:U_GOOD"], "policy": "any"}},
    )

    addrs, _ = resolve_approvers(routing, risk_level="medium", tool_name="any_tool")

    assert addrs == [("slack", "U_GOOD")]


# ── any / all policy preserved ────────────────────────────────────────────────


def test_all_policy_preserved_in_result() -> None:
    from fleetent.agent_config import resolve_approvers

    routing = _routing(
        by_risk={"high": {"approvers": ["slack:U1", "slack:U2"], "policy": "all"}},
    )

    _, policy = resolve_approvers(routing, risk_level="high", tool_name="any_tool")

    assert policy == "all"
