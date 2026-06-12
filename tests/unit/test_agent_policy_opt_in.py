"""Unit tests for opt-in tool visibility (sandbox-approval-relaxation, task 1).

`bash_exec` (host-execution, risk=high) is opt-in: an empty `allowed_tools`
(allow-all → None) or a bare `["*"]` wildcard MUST NOT implicitly grant it; only
an explicit literal name or an explicit pattern that covers it grants it. The
exclusion is applied at the tool-surface layer via `is_tool_visible`, which is the
single logical source shared by schema assembly and dispatch so the two stay
consistent.
"""

from __future__ import annotations

from fleetent.governance.agent_policy import (
    OPT_IN_TOOLS,
    check_tool_access,
    is_tool_visible,
)


def test_bash_exec_is_opt_in() -> None:
    assert "bash_exec" in OPT_IN_TOOLS


# ── allow-all (None) excludes opt-in, exposes the rest ────────────────────────


def test_allow_all_none_hides_opt_in() -> None:
    assert is_tool_visible("bash_exec", None) is False


def test_allow_all_none_exposes_non_opt_in() -> None:
    assert is_tool_visible("run_code", None) is True
    assert is_tool_visible("web_search", None) is True


# ── bare "*" wildcard behaves like allow-all: still hides opt-in ──────────────


def test_wildcard_star_hides_opt_in() -> None:
    assert is_tool_visible("bash_exec", ["*"]) is False


def test_wildcard_star_exposes_non_opt_in() -> None:
    assert is_tool_visible("run_code", ["*"]) is True


# ── explicit naming grants opt-in ─────────────────────────────────────────────


def test_explicit_literal_grants_opt_in() -> None:
    assert is_tool_visible("bash_exec", ["bash_exec"]) is True


def test_explicit_covering_pattern_grants_opt_in() -> None:
    # An explicit (non-bare-*) pattern that covers bash_exec grants it.
    assert is_tool_visible("bash_exec", ["bash_*"]) is True


def test_explicit_list_without_opt_in_hides_it() -> None:
    assert is_tool_visible("bash_exec", ["run_code", "web_search"]) is False


def test_explicit_list_exposes_listed_non_opt_in() -> None:
    assert is_tool_visible("run_code", ["run_code"]) is True
    assert is_tool_visible("web_search", ["run_code"]) is False


# ── schema visibility and dispatch share the same source ──────────────────────


def test_dispatch_and_schema_use_same_predicate() -> None:
    # check_tool_access (the dispatch predicate when allowed_tools is a list) must
    # agree with is_tool_visible for opt-in tools when the list is explicit/non-*.
    for allowed in (["bash_exec"], ["bash_*"]):
        assert is_tool_visible("bash_exec", allowed) is check_tool_access("bash_exec", allowed)
