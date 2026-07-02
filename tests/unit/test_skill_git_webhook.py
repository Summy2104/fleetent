"""Unit tests for skill_git_webhook_api pure helpers (no DB / no app).

webhook_decision gates a push hook: not-configured -> 404, no secret -> 403 (must NOT rely
on verify_signature, which returns True when secret is None), bad/missing signature -> 401,
valid HMAC -> 200. _status_payload exposes config + sync state but only credential env-NAMES,
never decrypted secret values.
"""

from __future__ import annotations

import hashlib
import hmac

from fleetent.platform.skill_management import skill_git_webhook_api as api


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_decision_not_configured() -> None:
    assert api.webhook_decision(None, None, b"x", None) == 404
    assert api.webhook_decision({"enabled": 0}, "s", b"x", None) == 404


def test_webhook_decision_no_secret_forbidden() -> None:
    # secret missing -> 403 even though verify_signature would pass-through on None
    assert api.webhook_decision({"enabled": 1}, None, b"x", None) == 403


def test_webhook_decision_bad_signature() -> None:
    assert api.webhook_decision({"enabled": 1}, "secret", b"body", "sha256=wrong") == 401
    assert api.webhook_decision({"enabled": 1}, "secret", b"body", None) == 401


def test_webhook_decision_valid() -> None:
    body = b"payload"
    assert api.webhook_decision({"enabled": 1}, "secret", body, _sig("secret", body)) == 200


def test_status_payload_redacts_credentials() -> None:
    config = {
        "enabled": 1,
        "provider": "bitbucket",
        "remote_url": "https://git.example/x.git",
        "branch": "main",
        "username_env": "GIT_USER",
        "token_env": "GIT_TOKEN",
        "webhook_secret_env": "WH_SECRET",
        "last_synced_commit": "abc",
        "last_sync_at": "2026-06-30T00:00:00+00:00",
        "last_sync_error": None,
    }
    payload = api._status_payload(config)

    assert payload["enabled"] is True
    assert payload["remote_url"] == "https://git.example/x.git"
    assert payload["last_synced_commit"] == "abc"
    # credential ENV NAMES are exposed (operators need them) ...
    assert payload["token_env"] == "GIT_TOKEN"
    # ... but no decrypted secret values are ever present
    assert "token" not in payload
    assert "password" not in payload
    assert "secret" not in payload


def test_status_payload_none_config() -> None:
    assert api._status_payload(None)["enabled"] is False
