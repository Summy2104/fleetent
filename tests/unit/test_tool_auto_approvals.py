"""Unit tests for the tool auto-approval fingerprint (approval-minimization)."""

from __future__ import annotations

from fleetent.governance.tool_auto_approvals_store import fingerprint


def test_fingerprint_stable() -> None:
    a = fingerprint("user:alice", "run_code", {"code": "print(1)"})
    b = fingerprint("user:alice", "run_code", {"code": "print(1)"})
    assert a == b


def test_fingerprint_key_order_independent() -> None:
    a = fingerprint("u", "t", {"a": 1, "b": 2})
    b = fingerprint("u", "t", {"b": 2, "a": 1})
    assert a == b


def test_fingerprint_sensitive_to_value() -> None:
    a = fingerprint("u", "t", {"code": "print(1)"})
    b = fingerprint("u", "t", {"code": "print(2)"})
    assert a != b


def test_fingerprint_sensitive_to_tool() -> None:
    a = fingerprint("u", "run_code", {"x": 1})
    b = fingerprint("u", "bash_exec", {"x": 1})
    assert a != b


def test_fingerprint_sensitive_to_scope() -> None:
    a = fingerprint("user:alice", "t", {"x": 1})
    b = fingerprint("user:bob", "t", {"x": 1})
    assert a != b


def test_fingerprint_is_hex_string() -> None:
    fp = fingerprint("u", "t", {"x": 1})
    assert isinstance(fp, str)
    assert len(fp) == 64  # sha256 hex
    int(fp, 16)  # parses as hex
