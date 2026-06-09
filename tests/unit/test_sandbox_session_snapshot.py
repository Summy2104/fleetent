"""Unit tests for sandbox session snapshot pure helpers (sandbox-session-snapshot)."""

from __future__ import annotations

from fleetent.integrations.sandbox import session_snapshot as ss


def test_snapshot_path_per_session() -> None:
    assert ss.snapshot_path("abc") == "/tmp/snap-abc.sh"


def test_snapshot_path_sanitises_unsafe_chars() -> None:
    p = ss.snapshot_path("user:U1/x")
    assert p.startswith("/tmp/snap-")
    assert p.endswith(".sh")
    # The session-derived filename part carries no path separator.
    assert "/" not in p[len("/tmp/snap-") :]


def test_cwd_marker_per_session_unique() -> None:
    assert ss.cwd_marker("a") != ss.cwd_marker("b")


def test_build_capture_script_captures_env_funcs_aliases() -> None:
    s = ss.build_capture_script("sess")
    assert "export -p" in s
    assert "declare -f" in s
    assert "alias -p" in s
    assert ss.snapshot_path("sess") in s


def test_wrap_command_sources_cds_evals_dumps_marks() -> None:
    w = ss.wrap_command("echo hi", "sess", "/workspace/sub")
    snap = ss.snapshot_path("sess")
    marker = ss.cwd_marker("sess")
    assert f"source {snap}" in w
    assert "/workspace/sub" in w
    assert "echo hi" in w
    assert f"export -p > {snap}" in w
    assert marker in w


def test_extract_cwd_returns_cwd_and_strips_marker() -> None:
    marker = ss.cwd_marker("sess")
    stdout = f"hello\n{marker}/workspace/sub{marker}\n"
    cwd, cleaned = ss.extract_cwd(stdout, "sess")
    assert cwd == "/workspace/sub"
    assert marker not in cleaned
    assert cleaned.strip() == "hello"


def test_extract_cwd_no_marker_returns_none_and_original() -> None:
    cwd, cleaned = ss.extract_cwd("plain output\n", "sess")
    assert cwd is None
    assert cleaned == "plain output\n"


def test_extract_cwd_takes_last_marker_pair() -> None:
    """If command output contains marker-like text, the real (last) pair wins."""
    marker = ss.cwd_marker("sess")
    stdout = f"{marker}/fake{marker}\nreal\n{marker}/workspace{marker}\n"
    cwd, cleaned = ss.extract_cwd(stdout, "sess")
    assert cwd == "/workspace"
    assert marker not in cleaned
