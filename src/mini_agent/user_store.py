"""SQLite-backed user store. Each user has a uuid id and an API key."""

import datetime
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path("data/users.db")


@dataclass
class User:
    id: str
    name: str
    api_key: str
    created_at: str


def create_user(name: str) -> User:
    """Create a new user with a generated uuid and API key."""
    _init_db()
    user = User(
        id=str(uuid.uuid4()),
        name=name,
        api_key=f"ma-{secrets.token_hex(32)}",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )
    with _conn() as conn:
        conn.execute(
            "INSERT INTO users (id, name, api_key, created_at) VALUES (?, ?, ?, ?)",
            (user.id, user.name, user.api_key, user.created_at),
        )
    return user


def get_by_api_key(api_key: str) -> User | None:
    """Look up a user by API key. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, api_key, created_at FROM users WHERE api_key = ?", (api_key,)
        ).fetchone()
    return User(*row) if row else None


def get_by_id(user_id: str) -> User | None:
    """Look up a user by id. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, api_key, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User(*row) if row else None


def list_users() -> list[User]:
    """Return all users ordered by created_at."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, api_key, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [User(*row) for row in rows]


def rotate_key(user_id: str) -> User:
    """Generate a new API key for user_id. Raises KeyError if user not found."""
    _init_db()
    new_key = f"ma-{secrets.token_hex(32)}"
    with _conn() as conn:
        updated = conn.execute(
            "UPDATE users SET api_key = ? WHERE id = ? RETURNING id, name, api_key, created_at",
            (new_key, user_id),
        ).fetchone()
    if updated is None:
        raise KeyError(f"User not found: {user_id}")
    return User(*updated)


def get_or_create_im_user(platform: str, platform_user_id: str) -> "User":
    from mini_agent.im_user_store import get_or_create

    return get_or_create(platform, platform_user_id)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                api_key    TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
