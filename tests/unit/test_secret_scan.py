"""Unit tests for the neutral secret-scan helpers (agent/platform decoupling).

These helpers were moved out of platform.config_validation into a neutral module so
agent-side config loading no longer imports platform. Behaviour is preserved verbatim.
"""

from fleetent import secret_scan


def test_flatten_nested():
    flat = dict(secret_scan.flatten({"a": {"b": "x"}, "c": [1, 2]}))
    assert flat["a.b"] == "x"
    assert flat["c.0"] == 1
    assert flat["c.1"] == 2


def test_flatten_scalar():
    assert secret_scan.flatten("v") == [("", "v")]


def test_looks_inline_secret_sk_token():
    assert secret_scan.looks_inline_secret("sk-aBcD1234EfGh5678IjKl") is True


def test_looks_inline_secret_long_token():
    assert secret_scan.looks_inline_secret("abcdefghijklmnopqrstuvwxyz0123") is True


def test_looks_inline_secret_short_plain_false():
    assert secret_scan.looks_inline_secret("hello world") is False


def test_looks_inline_secret_empty_false():
    assert secret_scan.looks_inline_secret("") is False
