"""Tests for sandbox output secret redaction (sandbox-output-redaction).

Pure string-transform tests: structured secrets are redacted with high precision,
named KEY=VALUE assignments conservatively, and ordinary output is left untouched.
"""

from __future__ import annotations

from fleetent.integrations.sandbox.redaction import redact_secrets

_PLACEHOLDER = "[REDACTED]"


def test_public_api_exports_redact_secrets() -> None:
    """redact_secrets is reachable from the package root, not just the submodule."""
    from fleetent.integrations.sandbox import redact_secrets as exported

    assert exported is redact_secrets


def test_redacts_pem_private_key_block() -> None:
    text = (
        "before\n-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA1234567890abcdef\nQyzAbC+/=\n"
        "-----END RSA PRIVATE KEY-----\nafter"
    )
    out = redact_secrets(text)
    assert "MIIEowIBAAKCAQEA1234567890abcdef" not in out
    assert "PRIVATE KEY" not in out
    assert _PLACEHOLDER in out
    assert out.startswith("before")
    assert out.endswith("after")


def test_redacts_jwt() -> None:
    jwt = "eyJhbGciOiJIUzI1Niup.eyJzdWIiOiIxMjM0NTY3ODkw.SflKxwRJSMeKKF2QT4fwpMeJf36"
    out = redact_secrets(f"token={jwt}")
    assert jwt not in out
    assert _PLACEHOLDER in out


def test_redacts_vendor_api_key_prefixes() -> None:
    for secret in (
        "sk-abcdefghijklmnopqrstuvwxyz0123",
        "sk-ant-api03-ABCDEFghijkl0123456789",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",
    ):
        out = redact_secrets(f"key is {secret} ok")
        assert secret not in out, secret
        assert _PLACEHOLDER in out


def test_redacts_connection_string_password_keeps_host() -> None:
    out = redact_secrets("postgres://admin:s3cr3tPw@db.internal:5432/app")
    assert "s3cr3tPw" not in out
    assert "postgres://" in out
    assert "db.internal" in out
    assert _PLACEHOLDER in out


def test_redacts_authorization_header_keeps_name() -> None:
    out = redact_secrets("Authorization: Bearer abc.def.ghi_secrettoken123")
    assert "abc.def.ghi_secrettoken123" not in out
    assert "Authorization" in out
    assert _PLACEHOLDER in out


def test_redacts_named_secret_assignments_keeps_key() -> None:
    for line in ("API_KEY=supersecretvalue", 'DB_PASSWORD="p@ss w0rd"', "ACCESS_KEY=AKIAonly"):
        out = redact_secrets(line)
        assert "supersecretvalue" not in out
        assert "p@ss" not in out
        assert _PLACEHOLDER in out
    assert "API_KEY=" in redact_secrets("API_KEY=supersecretvalue")


def test_does_not_redact_plain_text() -> None:
    plain = "The result is 42 and the sum of 1+2+3 = 6. All tests passed in 0.5s."
    assert redact_secrets(plain) == plain


def test_does_not_overredact_benign_key_like_names() -> None:
    """Bare KEY/AUTH substrings (AUTHOR, MONKEY) must NOT trigger value redaction."""
    benign = "AUTHOR=jane\nMONKEY=1\nKEYBOARD=qwerty"
    assert redact_secrets(benign) == benign
