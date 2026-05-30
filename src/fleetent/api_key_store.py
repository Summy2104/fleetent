"""Multiple API keys per user: issue/rotate/revoke, agent-level scope, usage tracking.

Keys are high-entropy random tokens, so a single SHA-256 hash (not a slow KDF) is
sufficient to avoid storing plaintext while keeping lookups fast.
"""

import datetime
import fnmatch
import hashlib
import json
import secrets

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

_COLS = (
    "id, user_id, prefix, scope, note, expires_at, revoked_at, "
    "created_at, last_used_at, last_ip, last_ua, call_count"
)
_FIELDS = [c.strip() for c in _COLS.split(",")]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def issue_key(
    user_id: str,
    scope: list[str] | None = None,
    note: str | None = None,
    expires_at: str | None = None,
) -> tuple[str, dict]:
    """Create a new key. Returns (plaintext shown once, metadata dict without plaintext)."""
    _init_db()
    plaintext = f"ma-{secrets.token_hex(32)}"
    prefix = plaintext[:11]
    now = _now()
    with _conn() as conn:
        cursor = conn.execute(
            """INSERT INTO api_keys
                   (user_id, key_hash, prefix, scope, note, expires_at, created_at, call_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            (user_id, _hash(plaintext), prefix, json.dumps(scope or ["*"]), note, expires_at, now),
        )
        key_id = cursor.lastrowid
    assert key_id is not None
    return plaintext, _get(key_id)


def revoke_key(key_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (_now(), key_id))


def rotate_key(key_id: int) -> tuple[str, dict]:
    """Revoke the key and issue a replacement for the same user with the same scope/note."""
    meta = _get(key_id)
    if meta is None:
        raise KeyError(f"key not found: {key_id}")
    revoke_key(key_id)
    return issue_key(
        meta["user_id"], scope=meta["scope"], note=meta["note"], expires_at=meta["expires_at"]
    )


def list_keys(user_id: str) -> list[dict]:
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM api_keys WHERE user_id = ? ORDER BY created_at", (user_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def resolve(plaintext: str) -> dict | None:
    """Return the key metadata if the key exists, is not revoked, and is not expired."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM api_keys WHERE key_hash = ?", (_hash(plaintext),)
        ).fetchone()
    if row is None:
        return None
    meta = _row_to_dict(row)
    if meta["revoked_at"] is not None:
        return None
    if meta["expires_at"] is not None and meta["expires_at"] <= _now():
        return None
    return meta


def record_usage(key_id: int, ip: str | None = None, ua: str | None = None) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            """UPDATE api_keys
               SET last_used_at = ?, last_ip = ?, last_ua = ?, call_count = call_count + 1
               WHERE id = ?""",
            (_now(), ip, ua, key_id),
        )


def check_scope(scope: list[str], agent_name: str) -> bool:
    """fnmatch the target agent against the key's scope allowlist (``["*"]`` = all)."""
    return any(fnmatch.fnmatch(agent_name, pattern) for pattern in scope)


def _get(key_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(f"SELECT {_COLS} FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row: tuple) -> dict:
    d = dict(zip(_FIELDS, row, strict=True))
    d["scope"] = json.loads(d["scope"]) if d["scope"] else ["*"]
    return d


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY,
                user_id      TEXT NOT NULL,
                key_hash     TEXT UNIQUE NOT NULL,
                prefix       TEXT NOT NULL,
                scope        TEXT NOT NULL DEFAULT '["*"]',
                note         TEXT,
                expires_at   TEXT,
                revoked_at   TEXT,
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                last_ip      TEXT,
                last_ua      TEXT,
                call_count   INTEGER NOT NULL DEFAULT 0
            )"""
        )
