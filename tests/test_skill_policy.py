"""Tests for per-agent skill access control (opt-in whitelist + blocklist)."""

from fleetent.agent_policy import check_skill_access


def test_none_allowed_skills_is_opt_in_deny():
    # opt-in: agent has not declared allowed_skills → no skill is injectable
    assert check_skill_access("deploy", None, None) is False


def test_empty_allowed_skills_denies():
    assert check_skill_access("deploy", [], None) is False


def test_exact_whitelist_match():
    assert check_skill_access("deploy", ["deploy"], None) is True


def test_whitelist_miss():
    assert check_skill_access("deploy", ["hr-*"], None) is False


def test_wildcard_whitelist_match():
    assert check_skill_access("hr-onboarding", ["hr-*"], None) is True


def test_hyphenated_skill_name_matches():
    assert check_skill_access("incident-response", ["incident-response"], None) is True


def test_blocklist_excludes_after_whitelist_hit():
    # whitelisted by hr-* but explicitly blocked
    assert check_skill_access("hr-payroll", ["hr-*"], ["hr-payroll"]) is False


def test_blocklist_none_is_no_exclusion():
    assert check_skill_access("hr-onboarding", ["hr-*"], None) is True


def test_blocklist_empty_is_no_exclusion():
    assert check_skill_access("hr-onboarding", ["hr-*"], []) is True


def test_blocklist_wildcard_excludes():
    assert check_skill_access("hr-payroll", ["*"], ["hr-*"]) is False
