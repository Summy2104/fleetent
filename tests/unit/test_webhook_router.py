"""Unit tests for webhook_router: payload extraction and signature verification."""

import hashlib
import hmac
import json

# NOTE: main dropped webhook_router.load_sources (yaml→runtime-API design); the merge
# kept zhangyang's yaml source model (load_sources retained), so this "is removed"
# regression test was removed. Webhook security (enabled flag + body-size limit) is
# now enforced at the /webhook endpoint — see tests/integration/test_webhook_server.py.


# ── extract_message ───────────────────────────────────────────────────────────


def test_extract_message_flat_field_substitution():
    from fleetent.webhook_router import extract_message

    result = extract_message("pushed to {ref}", {"ref": "main"})
    assert result == "pushed to main"


def test_extract_message_nested_field_substitution():
    from fleetent.webhook_router import extract_message

    result = extract_message(
        "PR merged: {repository[name]}",
        {"repository": {"name": "fleetent"}},
    )
    assert result == "PR merged: fleetent"


def test_extract_message_missing_key_falls_back_to_json():
    from fleetent.webhook_router import extract_message

    payload = {"event": "push"}
    result = extract_message("ref: {ref}", payload)
    assert result == json.dumps(payload)


def test_extract_message_none_template_falls_back_to_json():
    from fleetent.webhook_router import extract_message

    payload = {"event": "push"}
    result = extract_message(None, payload)
    assert result == json.dumps(payload)


# ── verify_signature ──────────────────────────────────────────────────────────


def _make_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_valid():
    from fleetent.webhook_router import verify_signature

    body = b'{"event": "push"}'
    sig = _make_sig("mysecret", body)
    assert verify_signature("mysecret", body, sig) is True


def test_verify_signature_invalid():
    from fleetent.webhook_router import verify_signature

    body = b'{"event": "push"}'
    assert verify_signature("mysecret", body, "sha256=badhex") is False


def test_verify_signature_no_secret_always_returns_true():
    from fleetent.webhook_router import verify_signature

    assert verify_signature(None, b"anything", None) is True
    assert verify_signature(None, b"anything", "sha256=whatever") is True


def test_verify_signature_missing_header_returns_false_when_secret_set():
    from fleetent.webhook_router import verify_signature

    assert verify_signature("secret", b"body", None) is False


def test_verify_signature_uses_compare_digest(monkeypatch):
    """Ensure timing-safe comparison is used (compare_digest, not ==)."""
    import fleetent.webhook_router as wr

    calls: list = []

    original = hmac.compare_digest

    def capturing_compare(a: str, b: str) -> bool:
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr("fleetent.webhook_router.hmac_compare_digest", capturing_compare)
    body = b"test"
    sig = _make_sig("s", body)
    wr.verify_signature("s", body, sig)
    assert len(calls) == 1


# ── WebhookSource model: reply_target (live-webhooks) ─────────────────────────


def test_source_reply_target_defaults_none():
    from fleetent.webhook_router import WebhookSource

    s = WebhookSource(id="github-ci", user_id="u1")
    assert s.reply_target is None


def test_source_reply_target_set():
    from fleetent.webhook_router import WebhookSource

    s = WebhookSource(id="github-ci", user_id="u1", reply_target="u-internal-42")
    assert s.reply_target == "u-internal-42"
