"""Public redaction API on the logging substrate.

Redaction used to live in three places: structured_logging's private helpers,
knowledge_base.operations._sanitize_text (word-pattern), and cross-package
private imports from platform_cli/diagnostics. The substrate now exposes
redact_text/redact_value as the single public surface.
"""

from __future__ import annotations

from fleetent.structured_logging import redact_text, redact_value


def test_redact_text_masks_secret_word_patterns():
    assert redact_text("token: abc123") == "token [REDACTED]"
    assert redact_text("api_key=sk-live-42 rest") == "api_key [REDACTED] rest"
    assert redact_text("credential - hunter2,next") == "credential [REDACTED],next"


def test_redact_text_keeps_existing_text_redactions():
    # The invariant is "nothing sensitive survives", not an exact output shape —
    # the word pattern may further rewrite already-masked labels.
    out = redact_text("Authorization: Bearer abcdef0123456789 mail me at a@b.co")
    assert "abcdef0123456789" not in out
    assert "a@b.co" not in out
    assert "[REDACTED" in out


def test_redact_text_passes_benign_text_through():
    assert redact_text("connector is reachable") == "connector is reachable"


def test_redact_value_masks_sensitive_keys_recursively():
    payload = {"bot_token": "xoxb-1", "nested": [{"password": "p"}], "count": 3}
    out = redact_value(payload)
    assert out["bot_token"] == "[REDACTED:token]"
    assert out["nested"][0]["password"] == "[REDACTED:token]"
    assert out["count"] == 3
