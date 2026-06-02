from fleetent.governance.agent_policy import check_tool_access


def test_exact_match():
    assert check_tool_access("shell", ["shell", "github__create_issue"]) is True


def test_no_match():
    assert check_tool_access("shell", ["github__*"]) is False


def test_wildcard_match():
    assert check_tool_access("github__create_issue", ["github__*"]) is True


def test_wildcard_no_match():
    assert check_tool_access("linear__create_ticket", ["github__*"]) is False


def test_empty_allowed_tools():
    assert check_tool_access("shell", []) is False


def test_multiple_patterns():
    assert check_tool_access("shell", ["github__*", "shell"]) is True
