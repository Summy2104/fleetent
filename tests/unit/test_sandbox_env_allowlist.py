"""Unit tests for build_sandbox_env name allowlist (sandbox-hardening, task 1)."""

from __future__ import annotations

from fleetent.integrations.sandbox.secrets import build_sandbox_env


def test_allowlist_keeps_only_listed_names() -> None:
    env = build_sandbox_env(agent_env={"FOO": "1", "BAR": "2"}, allowlist={"FOO"})
    assert env == {"FOO": "1"}


def test_allowlist_none_keeps_current_behavior() -> None:
    env = build_sandbox_env(agent_env={"FOO": "1", "BAR": "2"})
    assert env == {"FOO": "1", "BAR": "2"}


def test_allowlist_does_not_exempt_sensitive() -> None:
    # API_KEY is allowlisted but still sensitive → dropped by the blocklist.
    env = build_sandbox_env(agent_env={"API_KEY": "x", "FOO": "1"}, allowlist={"API_KEY", "FOO"})
    assert "API_KEY" not in env
    assert env == {"FOO": "1"}


def test_empty_allowlist_drops_everything() -> None:
    env = build_sandbox_env(agent_env={"FOO": "1"}, allowlist=set())
    assert env == {}
