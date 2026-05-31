"""Unit tests for webhook_router: config loading, payload extraction, signature verification."""

import hashlib
import hmac
import json

import yaml

# ── load_sources ─────────────────────────────────────────────────────────────


def test_load_sources_returns_sources_from_yaml(tmp_path):
    from fleetent import webhook_router as wr

    cfg = tmp_path / "webhooks.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "sources": [
                    {
                        "id": "gh",
                        "user_id": "u-1",
                        "secret": "s3cr3t",
                        "agent_name": "devops",
                        "message_template": "push: {ref}",
                    },
                ]
            }
        )
    )
    sources = wr.load_sources(cfg)
    assert "gh" in sources
    s = sources["gh"]
    assert s.id == "gh"
    assert s.user_id == "u-1"
    assert s.secret == "s3cr3t"
    assert s.agent_name == "devops"
    assert s.message_template == "push: {ref}"


def test_load_sources_missing_file_returns_empty(tmp_path):
    from fleetent import webhook_router as wr

    sources = wr.load_sources(tmp_path / "nonexistent.yaml")
    assert sources == {}


def test_load_sources_optional_fields_default_to_none(tmp_path):
    from fleetent import webhook_router as wr

    cfg = tmp_path / "webhooks.yaml"
    cfg.write_text(yaml.dump({"sources": [{"id": "bare", "user_id": "u-2"}]}))
    s = wr.load_sources(cfg)["bare"]
    assert s.secret is None
    assert s.agent_name is None
    assert s.message_template is None


def test_load_sources_multiple_entries(tmp_path):
    from fleetent import webhook_router as wr

    cfg = tmp_path / "webhooks.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "sources": [
                    {"id": "a", "user_id": "u-1"},
                    {"id": "b", "user_id": "u-2"},
                ]
            }
        )
    )
    sources = wr.load_sources(cfg)
    assert set(sources.keys()) == {"a", "b"}


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
