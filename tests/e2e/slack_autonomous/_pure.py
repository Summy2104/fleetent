"""Pure, network-free helper logic — unit-testable in isolation.

These functions hold the only decision logic the helper has (message filtering,
JSON result shaping, precondition reporting, filename safety). The actual Slack
Web API calls live in ``helper.py`` and import from here. No LLM, no verdict.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

Message = dict[str, Any]


def filter_new_bot_messages(
    messages: list[Message], bot_user_id: str, after_ts: str | None
) -> list[Message]:
    """Return only messages authored by ``bot_user_id`` strictly newer than the cursor.

    Excludes the test user's own messages and anything at or before ``after_ts``
    (a Slack ``ts`` string). ``after_ts`` of ``None``/``""`` means no lower bound.
    Result is sorted ascending by ``ts`` so the caller reads replies in order.
    """
    cursor = float(after_ts) if after_ts not in (None, "") else None
    picked = [
        m
        for m in messages
        if m.get("user") == bot_user_id and (cursor is None or float(m["ts"]) > cursor)
    ]
    return sorted(picked, key=lambda m: float(m["ts"]))


def ok_result(**fields: Any) -> dict[str, Any]:
    """A success result object: ``{"ok": True, **fields}``."""
    return {"ok": True, **fields}


def error_result(message: str, **fields: Any) -> dict[str, Any]:
    """An error result object carrying an ``error`` field."""
    return {"ok": False, "error": message, **fields}


def blocked_result(missing: Iterable[str]) -> dict[str, Any]:
    """A blocked result naming the missing preconditions (never fabricate success)."""
    return {"ok": False, "status": "blocked", "missing": list(missing)}


def dump_json(result: dict[str, Any]) -> str:
    """Serialize a result as a single JSON object (UTF-8, no ASCII escaping)."""
    return json.dumps(result, ensure_ascii=False)


def exit_code_for(result: dict[str, Any]) -> int:
    """Process exit code: 0 when ``ok`` is truthy, else 1."""
    return 0 if result.get("ok") else 1


def build_resolve_report(
    *,
    token_ok: bool,
    bot_user_id: str | None,
    bot_found: bool,
    channel_ok: bool,
    missing_scopes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Summarize precondition checks into a ready/blocked result.

    Names each missing item (``token`` / ``bot[:id]`` / ``channel`` / ``scope:<s>``)
    so the driver can report exactly what to fix, rather than fabricating success.
    """
    missing: list[str] = []
    if not token_ok:
        missing.append("token")
    if not bot_found:
        missing.append(f"bot:{bot_user_id}" if bot_user_id else "bot")
    if not channel_ok:
        missing.append("channel")
    missing.extend(f"scope:{s}" for s in missing_scopes)
    if missing:
        return blocked_result(missing)
    return ok_result(status="ready", bot_user_id=bot_user_id)


def safe_local_filename(name: str) -> str:
    """Sanitize a downloaded filename to a bare basename, defeating path escape."""
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f]", "", base).strip().lstrip(".")
    return base or "download"
