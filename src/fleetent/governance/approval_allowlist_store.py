"""Agent-side allow-always store: persists approver-granted permanent allowances.

A grant keys on a fingerprint of (requester scope, tool, normalized args). Once an
approver grants "always" for a call, future calls with the same fingerprint are
auto-approved at the gate without re-prompting (approval-minimization).

Schema owner: agent_state.db via per-agent MIGRATIONS (v13).  Connection is
injected via set_state_db() at agent boot — no ensure_schema, no DB_PATH.
Uses named parameters throughout.  No platform imports.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fleetent.db import SQLiteDatabase

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot."""
    global _state_db
    _state_db = db


def database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "approval_allowlist_store: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


def fingerprint(scope_key: str, tool_name: str, tool_args: dict[str, Any]) -> str:
    """Stable hex digest of (scope, tool, canonical args).

    Canonical JSON (sorted keys, no whitespace) makes the digest independent of key
    order but sensitive to any value/tool/scope difference — so a different operation
    never reuses another's grant.
    """
    canonical = json.dumps(tool_args, sort_keys=True, separators=(",", ":"), default=str)
    payload = "\x00".join((scope_key, tool_name, canonical))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_allowed(fp: str) -> bool:
    """Whether a fingerprint has a persistent allow-always grant."""
    row = database().execute(
        "SELECT 1 FROM approval_allowlist WHERE fingerprint = :fp LIMIT 1",
        {"fp": fp},
    ).fetchone()
    return row is not None


def add_grant(
    *,
    fingerprint: str,
    scope_key: str,
    tool_name: str,
    created_at: str,
    created_by: str | None = None,
) -> None:
    """Persist an allow-always grant. Idempotent on the fingerprint primary key."""
    database().execute(
        """
        INSERT INTO approval_allowlist (fingerprint, scope_key, tool_name, created_at, created_by)
        VALUES (:fingerprint, :scope_key, :tool_name, :created_at, :created_by)
        ON CONFLICT(fingerprint) DO NOTHING
        """,
        {
            "fingerprint": fingerprint,
            "scope_key": scope_key,
            "tool_name": tool_name,
            "created_at": created_at,
            "created_by": created_by,
        },
    )


def list_grants() -> list[dict[str, Any]]:
    """Return all allow-always grants (newest first)."""
    rows = database().execute(
        "SELECT fingerprint, scope_key, tool_name, created_at, created_by "
        "FROM approval_allowlist ORDER BY created_at DESC"
    ).fetchall()
    return list(rows)
