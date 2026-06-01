"""Webhook source configuration, payload extraction, and HMAC signature verification."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

hmac_compare_digest = hmac.compare_digest


@dataclass
class WebhookSource:
    id: str
    user_id: str
    secret: str | None = None
    agent_name: str | None = None
    message_template: str | None = None


def extract_message(template: str | None, payload: Any) -> str:
    """Extract message text from payload using template substitution.

    Supports flat {key} and one-level nested {key[subkey]} syntax.
    Falls back to json.dumps(payload) on any substitution failure.
    """
    if template is None:
        return json.dumps(payload)
    try:
        return template.format_map(payload)
    except (KeyError, IndexError, AttributeError, TypeError):
        return json.dumps(payload)


def verify_signature(secret: str | None, body: bytes, header: str | None) -> bool:
    """Verify HMAC-SHA256 signature from X-Hub-Signature-256 header.

    Returns True unconditionally when no secret is configured.
    """
    if secret is None:
        return True
    if header is None:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac_compare_digest(expected, header)
