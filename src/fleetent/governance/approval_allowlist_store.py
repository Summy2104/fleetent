"""Agent-side allow-always store: persists approver-granted permanent allowances.

A grant keys on a fingerprint of (requester scope, tool, normalized args). Once an
approver grants "always" for a call, future calls with the same fingerprint are
auto-approved at the gate without re-prompting (approval-minimization).

Schema owner: this module — not Alembic (pure agent-side table, like approval_store).
Uses fleetent.db.SQLiteDatabase with named params throughout. No platform imports.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fleetent import paths
from fleetent.db import SQLiteDatabase

DB_PATH = paths.data_dir() / "fleetent.db"


def fingerprint(scope_key: str, tool_name: str, tool_args: dict[str, Any]) -> str:
    """Stable hex digest of (scope, tool, canonical args).

    Canonical JSON (sorted keys, no whitespace) makes the digest independent of key
    order but sensitive to any value/tool/scope difference — so a different operation
    never reuses another's grant.
    """
    canonical = json.dumps(tool_args, sort_keys=True, separators=(",", ":"), default=str)
    payload = "\x00".join((scope_key, tool_name, canonical))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _db(db_path: Path | None = None) -> SQLiteDatabase:
    return SQLiteDatabase(path=db_path or DB_PATH)


def ensure_schema(db_path: Path | None = None) -> None:
    """Create the approval_allowlist table if it does not exist. Idempotent."""
    _db(db_path).execute(
        """
        CREATE TABLE IF NOT EXISTS approval_allowlist (
            fingerprint TEXT PRIMARY KEY,
            scope_key   TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            created_by  TEXT
        )
        """
    )


def is_allowed(fp: str, db_path: Path | None = None) -> bool:
    """Whether a fingerprint has a persistent allow-always grant."""
    ensure_schema(db_path)
    row = (
        _db(db_path)
        .execute(
            "SELECT 1 FROM approval_allowlist WHERE fingerprint = :fp LIMIT 1",
            {"fp": fp},
        )
        .fetchone()
    )
    return row is not None


def add_grant(
    *,
    fingerprint: str,
    scope_key: str,
    tool_name: str,
    created_at: str,
    created_by: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Persist an allow-always grant. Idempotent on the fingerprint primary key."""
    ensure_schema(db_path)
    _db(db_path).execute(
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


def list_grants(db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return all allow-always grants (newest first)."""
    ensure_schema(db_path)
    rows = (
        _db(db_path)
        .execute(
            "SELECT fingerprint, scope_key, tool_name, created_at, created_by "
            "FROM approval_allowlist ORDER BY created_at DESC"
        )
        .fetchall()
    )
    return list(rows)
