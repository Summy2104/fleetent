"""Webhook source configuration, payload extraction, and HMAC signature verification."""

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

hmac_compare_digest = hmac.compare_digest


@dataclass
class WebhookSource:
    id: str
    user_id: str
    secret: str | None = None
    agent_name: str | None = None
    message_template: str | None = None
    # Optional IM delivery target for the run result (live-webhooks): an internal user_id
    # to DM the result to. None = no-op reply (result recorded in eval trace only).
    reply_target: str | None = None


def load_sources(path: Path) -> dict[str, WebhookSource]:
    """Load webhook source definitions from a YAML file. Returns {} if file missing."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    result: dict[str, WebhookSource] = {}
    for entry in raw.get("sources", []):
        src = WebhookSource(
            id=entry["id"],
            user_id=entry["user_id"],
            secret=entry.get("secret"),
            agent_name=entry.get("agent_name"),
            message_template=entry.get("message_template"),
            reply_target=entry.get("reply_target"),
        )
        result[src.id] = src
    return result


def sources_from_settings(source_settings: Any) -> dict[str, WebhookSource]:
    """Resolve standalone ``agent.yaml`` webhook source settings into neutral sources.

    Each ``WebhookSourceSettings`` carries ``secret_env`` (an env var NAME); this resolves
    it against ``os.environ`` so HMAC verification sees the secret value. An unset/missing
    env var resolves to ``None`` (open verification, per ``verify_signature``). Accepts any
    iterable of objects exposing the source attributes (duck-typed to avoid importing config).
    """
    result: dict[str, WebhookSource] = {}
    for entry in source_settings or []:
        secret_env = getattr(entry, "secret_env", None)
        secret = os.environ.get(secret_env) if secret_env else None
        src = WebhookSource(
            id=entry.id,
            user_id=entry.user_id,
            secret=secret or None,
            agent_name=getattr(entry, "agent_name", None),
            message_template=getattr(entry, "message_template", None),
            reply_target=getattr(entry, "reply_target", None),
        )
        result[src.id] = src
    return result


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
