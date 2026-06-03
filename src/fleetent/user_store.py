"""SQLite-backed user store. Each user has a uuid id and an API key."""

import datetime
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_PATH = Path("data/fleetent.db")


@dataclass
class User:
    id: str
    name: str
    api_key: str
    created_at: str
    email: str | None = None
    role: str = "viewer"
    status: str = "active"
    must_reset: int = 0
    password_hash: str | None = None
    totp_secret: str | None = None


_FULL_COLS = (
    "id, name, api_key, created_at, email, role, status, must_reset, password_hash, totp_secret"
)


def create_user(name: str, email: str | None = None) -> User:
    """Create a new user with a generated uuid and API key."""
    _init_db()
    user = User(
        id=str(uuid.uuid4()),
        name=name,
        api_key=f"ma-{secrets.token_hex(32)}",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        email=email,
    )
    with _conn() as conn:
        conn.execute(
            "INSERT INTO users (id, name, api_key, created_at, email) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.name, user.api_key, user.created_at, user.email),
        )
    return user


def authenticate(plaintext: str) -> tuple[User, dict[str, Any]] | None:
    """Resolve a plaintext API key to (User, key_metadata).

    Checks the api_keys table first (validity handled there), then falls back to the
    legacy users.api_key column for keys not yet migrated. Returns None if the key is
    invalid/revoked/expired or the owning user is blocked.
    """
    from fleetent.platform.user_management import api_key_store

    _init_db()
    meta = api_key_store.resolve(plaintext)
    if meta is not None:
        user = get_by_id(meta["user_id"])
        if user is None or user.status == "blocked":
            return None
        return user, meta

    # Legacy fallback: key still lives only in the users.api_key column.
    user = _get_by_legacy_key(plaintext)
    if user is None or user.status == "blocked":
        return None
    return user, {"id": None, "user_id": user.id, "scope": ["*"], "prefix": plaintext[:11]}


def get_by_api_key(api_key: str) -> User | None:
    """Look up a user by API key (delegates to authenticate). Returns None if invalid."""
    result = authenticate(api_key)
    return result[0] if result else None


def _get_by_legacy_key(api_key: str) -> User | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_FULL_COLS} FROM users WHERE api_key = ?", (api_key,)
        ).fetchone()
    return User(*row) if row else None


def migrate_api_keys() -> list[str]:
    """Move legacy users.api_key values into the api_keys table. Idempotent.

    Returns the list of user ids whose keys were migrated this run.
    """
    from fleetent.platform.user_management import api_key_store

    _init_db()
    api_key_store._init_db()
    moved: list[str] = []
    with _conn() as conn:
        users = conn.execute("SELECT id, api_key FROM users WHERE api_key IS NOT NULL").fetchall()
        existing = {r[0] for r in conn.execute("SELECT key_hash FROM api_keys").fetchall()}
    for user_id, api_key in users:
        if api_key_store._hash(api_key) in existing:
            continue
        import datetime as _dt

        with _conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO api_keys
                       (user_id, key_hash, prefix, scope, note, created_at, call_count)
                   VALUES (?, ?, ?, '["*"]', 'migrated', ?, 0)""",
                (
                    user_id,
                    api_key_store._hash(api_key),
                    api_key[:11],
                    _dt.datetime.now(_dt.UTC).isoformat(),
                ),
            )
        moved.append(user_id)
    return moved


def get_by_id(user_id: str) -> User | None:
    """Look up a user by id. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(f"SELECT {_FULL_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(*row) if row else None


def get_by_email(email: str) -> User | None:
    """Look up a user by email. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(f"SELECT {_FULL_COLS} FROM users WHERE email = ?", (email,)).fetchone()
    return User(*row) if row else None


def list_users() -> list[User]:
    """Return all users ordered by created_at."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(f"SELECT {_FULL_COLS} FROM users ORDER BY created_at").fetchall()
    return [User(*row) for row in rows]


def rotate_key(user_id: str) -> User:
    """Generate a new API key for user_id. Raises KeyError if user not found."""
    _init_db()
    new_key = f"ma-{secrets.token_hex(32)}"
    with _conn() as conn:
        updated = conn.execute(
            f"UPDATE users SET api_key = ? WHERE id = ? RETURNING {_FULL_COLS}",
            (new_key, user_id),
        ).fetchone()
    if updated is None:
        raise KeyError(f"User not found: {user_id}")
    return User(*updated)


def get_builtin_admin() -> User | None:
    """Return the built-in admin user, if seeded."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_FULL_COLS} FROM users WHERE role = 'built_in_admin' LIMIT 1"
        ).fetchone()
    return User(*row) if row else None


def set_role(user_id: str, role: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin" and role != "built_in_admin":
        raise PermissionError("built-in admin cannot be demoted")
    _update_field(user_id, "role", role)


def set_status(user_id: str, status: str) -> None:
    _update_field(user_id, "status", status)


def set_password(user_id: str, password_hash: str, must_reset: bool = False) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_reset = ? WHERE id = ?",
            (password_hash, int(must_reset), user_id),
        )


def set_must_reset(user_id: str, must_reset: bool) -> None:
    _update_field(user_id, "must_reset", int(must_reset))


def set_totp_secret(user_id: str, secret: str | None) -> None:
    _update_field(user_id, "totp_secret", secret)


def create_web_user(
    email: str,
    name: str,
    password_hash: str | None = None,
    must_reset: bool = False,
    role: str = "viewer",
) -> User:
    """Create a web user (admin-initiated). Rejects duplicate or registration-blocked emails.

    An empty/whitespace email is treated as "no email" (stored as NULL) and is exempt from the
    duplicate check, so several email-less users (e.g. IM-only) can coexist.
    """
    _init_db()
    from fleetent.governance import blocklist

    normalized = email.strip() or None
    if normalized is not None:
        if blocklist.is_registration_blocked(normalized):
            raise PermissionError(f"email blocked from registration: {normalized}")
        if get_by_email(normalized) is not None:
            raise ValueError(f"email already exists: {normalized}")
    user = create_user(name=name, email=normalized)
    if role != "viewer":
        set_role(user.id, role)
    if password_hash is not None:
        set_password(user.id, password_hash, must_reset=must_reset)
    elif must_reset:
        set_must_reset(user.id, True)
    result = get_by_id(user.id)
    assert result is not None
    return result


def bulk_import_users(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Create users from parsed rows. Returns {created: [ids], failed: [{email, error}]}."""
    created: list[str] = []
    failed: list[dict[str, str]] = []
    for row in rows:
        email = row.get("email", "")
        try:
            user = create_web_user(email, row.get("name") or email)
            created.append(user.id)
        except (ValueError, PermissionError) as exc:
            failed.append({"email": email, "error": str(exc)})
    return {"created": created, "failed": failed}


def disable_user(user_id: str) -> None:
    _guard_not_builtin_admin(user_id, "disable")
    set_status(user_id, "disabled")


def delete_user(user_id: str) -> None:
    _guard_not_builtin_admin(user_id, "delete")
    _init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _guard_not_builtin_admin(user_id: str, op: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin":
        raise PermissionError(f"built-in admin cannot be {op}d")


def _update_field(user_id: str, column: str, value: object) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (value, user_id))


def get_or_create_im_user(platform: str, platform_user_id: str) -> "User":
    from fleetent.im_user_store import get_or_create

    return get_or_create(platform, platform_user_id)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


_EXTRA_COLUMNS = (
    ("email", "TEXT"),
    ("password_hash", "TEXT"),
    ("role", "TEXT NOT NULL DEFAULT 'viewer'"),
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("must_reset", "INTEGER NOT NULL DEFAULT 0"),
    ("totp_secret", "TEXT"),
)


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
        existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        for column, decl in _EXTRA_COLUMNS:
            if column not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} {decl}")
