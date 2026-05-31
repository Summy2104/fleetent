"""One-time invite links: create a token, accept it to activate a user with a password."""

import datetime
import hashlib
import secrets
from typing import Any

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def create_invite(email: str, ttl_seconds: int = 86400) -> tuple[str, dict[str, Any]]:
    """Create a one-time invite for an email. Returns (token shown once, metadata)."""
    _init_db()
    token = secrets.token_urlsafe(24)
    expires_at = (_now() + datetime.timedelta(seconds=ttl_seconds)).isoformat()
    with _conn() as conn:
        cursor = conn.execute(
            """INSERT INTO invites (email, token_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?)""",
            (email, _hash(token), expires_at, _now().isoformat()),
        )
        invite_id = cursor.lastrowid
    return token, {"id": invite_id, "email": email, "expires_at": expires_at}


def accept_invite(token: str, password_hash: str) -> object:
    """Validate a token, create the user with the password, issue the first key, burn the token."""
    from fleetent import api_key_store, user_store

    _init_db()
    now_iso = _now().isoformat()
    with _conn() as conn:
        row = conn.execute(
            """SELECT id, email, expires_at, used_at FROM invites WHERE token_hash = ?""",
            (_hash(token),),
        ).fetchone()
    if row is None:
        raise ValueError("invite invalid")
    invite_id, email, expires_at, used_at = row
    if used_at is not None or expires_at <= now_iso:
        raise ValueError("invite invalid")
    user = user_store.create_web_user(email, name=email, password_hash=password_hash)
    api_key_store.issue_key(user.id, scope=["*"], note="invite")
    with _conn() as conn:
        conn.execute("UPDATE invites SET used_at = ? WHERE id = ?", (now_iso, invite_id))
    return user


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS invites (
                id         INTEGER PRIMARY KEY,
                email      TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used_at    TEXT,
                created_at TEXT NOT NULL
            )"""
        )
