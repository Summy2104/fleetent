import json

from fleetent.observability import build_tool_args_summary


def test_sensitive_named_args_are_redacted():
    summary = build_tool_args_summary({"api_key": "sk-secret-value", "path": "/tmp/x"})

    assert "sk-secret-value" not in summary
    parsed = json.loads(summary)
    assert parsed["api_key"] == "[REDACTED]"
    assert parsed["path"] == "/tmp/x"


def test_token_named_arg_is_redacted():
    summary = build_tool_args_summary({"access_token": "t-123", "n": 5})

    assert "t-123" not in summary
    assert json.loads(summary)["access_token"] == "[REDACTED]"


def test_large_args_are_truncated_with_marker_and_bounded():
    summary = build_tool_args_summary({"code": "x" * 5000})

    assert len(summary) <= 2048
    assert summary.endswith("...[truncated]")


def test_string_args_passthrough_when_not_json_object():
    # A non-dict JSON value (or malformed) is summarized as-is, still bounded.
    summary = build_tool_args_summary("plain string args")

    assert summary == "plain string args"
