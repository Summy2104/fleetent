"""SQLite-backed user store. Each user has a uuid id and an API key."""

import datetime
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fleetent import paths

# Kept for test legacy-shim and module-boundary detection; not used as a DB entry point
# after retire-raw-sqlite-connect (all connections go through db.py boundary).
DB_PATH = paths.data_dir() / "management.db"

# Injectable hook for resolving api_keys table entries.
# Platform startup wires this to api_key_store.resolve; standalone agents leave it None,
# falling back to the legacy users.api_key column only (no platform import needed).
_api_key_resolver: Callable[[str], dict[str, Any] | None] | None = None


def set_api_key_resolver(resolver: Callable[[str], dict[str, Any] | None]) -> None:
    """Wire the platform api_keys resolver into the user store.

    Called once by the platform server lifespan. Must not be called by agent runtime code.
    """
    global _api_key_resolver
    _api_key_resolver = resolver


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
    tenant_id: str = "default"


_FULL_COLS = (
    "id, name, api_key, created_at, email, role, status, must_reset, password_hash, tenant_id"
)


def _db():
    from fleetent.config import Settings
    from fleetent.db import create_database

    return create_database(Settings().database_url)


def _conn():
    """Compatibility shim for platform stores that import _conn from user_store.

    Returns a sqlite3.Connection that (a) reads DATABASE_URL from Settings (same source
    as _db()) and (b) sets WAL+busy_timeout via db.py._connect, so callers get the
    same durability guarantees without needing to migrate to SQLiteDatabase yet.
    Callers use `with _conn() as conn: conn.execute(...)` — sqlite3.Connection is a
    context manager that auto-commits / rolls back.
    """
    import sqlite3  # noqa: PLC0415 — kept local, this is a shim on the removal path

    from fleetent.db import _connect

    db = _db()  # resolves Settings().database_url to a Path
    db.path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db.path)
    conn.row_factory = sqlite3.Row
    return conn


def create_user(name: str, email: str | None = None, tenant_id: str = "default") -> User:
    """Create a new user with a generated uuid and API key."""
    user = User(
        id=str(uuid.uuid4()),
        name=name,
        api_key=f"ma-{secrets.token_hex(32)}",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        email=email,
        tenant_id=tenant_id,
    )
    with _db().transaction() as conn:
        conn.execute(
            "INSERT INTO users (id, name, api_key, created_at, email, tenant_id)"
            " VALUES (:id, :name, :api_key, :created_at, :email, :tenant_id)",
            {
                "id": user.id,
                "name": user.name,
                "api_key": user.api_key,
                "created_at": user.created_at,
                "email": user.email,
                "tenant_id": user.tenant_id,
            },
        )
    return user


def authenticate(plaintext: str) -> tuple[User, dict[str, Any]] | None:
    """Resolve a plaintext API key to (User, key_metadata).

    When the platform api_keys resolver is wired (set_api_key_resolver was called at
    startup), checks the api_keys table first. Falls back to the legacy users.api_key
    column for standalone agents or unmigrated keys. Returns None if the key is
    invalid/revoked/expired or the owning user is blocked.
    """
    if _api_key_resolver is not None:
        meta = _api_key_resolver(plaintext)
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
    row = (
        _db()
        .execute(f"SELECT {_FULL_COLS} FROM users WHERE api_key = :api_key", {"api_key": api_key})
        .fetchone()
    )
    return _row_to_user(row) if row else None


def migrate_api_keys() -> list[str]:
    """Move legacy users.api_key values into the api_keys table. Idempotent.

    Returns the list of user ids whose keys were migrated this run.
    """
    from fleetent.platform.user_management import api_key_store

    db = _db()
    moved: list[str] = []
    users = db.execute("SELECT id, api_key FROM users WHERE api_key IS NOT NULL").fetchall()
    existing = {r["key_hash"] for r in db.execute("SELECT key_hash FROM api_keys").fetchall()}
    for row in users:
        user_id, api_key = row["id"], row["api_key"]
        if api_key_store._hash(api_key) in existing:
            continue
        import datetime as _dt

        with db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO api_keys
                       (user_id, key_hash, prefix, scope, note, created_at, call_count)
                   VALUES (:user_id, :key_hash, :prefix, '["*"]', 'migrated', :created_at, 0)""",
                {
                    "user_id": user_id,
                    "key_hash": api_key_store._hash(api_key),
                    "prefix": api_key[:11],
                    "created_at": _dt.datetime.now(_dt.UTC).isoformat(),
                },
            )
        moved.append(user_id)
    return moved


def get_by_id(user_id: str) -> User | None:
    """Look up a user by id. Returns None if not found."""
    row = (
        _db().execute(f"SELECT {_FULL_COLS} FROM users WHERE id = :id", {"id": user_id}).fetchone()
    )
    return _row_to_user(row) if row else None


def get_by_email(email: str) -> User | None:
    """Look up a user by email. Returns None if not found."""
    row = (
        _db()
        .execute(f"SELECT {_FULL_COLS} FROM users WHERE email = :email", {"email": email})
        .fetchone()
    )
    return _row_to_user(row) if row else None


def list_users() -> list[User]:
    """Return all users ordered by created_at."""
    rows = _db().execute(f"SELECT {_FULL_COLS} FROM users ORDER BY created_at").fetchall()
    return [_row_to_user(r) for r in rows]


def rotate_key(user_id: str) -> User:
    """Generate a new API key for user_id. Raises KeyError if user not found."""
    new_key = f"ma-{secrets.token_hex(32)}"
    row = (
        _db()
        .execute(
            f"UPDATE users SET api_key = :key WHERE id = :id RETURNING {_FULL_COLS}",
            {"key": new_key, "id": user_id},
        )
        .fetchone()
    )
    if row is None:
        raise KeyError(f"User not found: {user_id}")
    return _row_to_user(row)


def get_builtin_admin() -> User | None:
    """Return the built-in admin user, if seeded."""
    row = (
        _db()
        .execute(f"SELECT {_FULL_COLS} FROM users WHERE role = 'built_in_admin' LIMIT 1")
        .fetchone()
    )
    return _row_to_user(row) if row else None


# Sentinel owner for rows backfilled before a built-in admin exists; reassigned to the
# real admin owner on next seed.
SYSTEM_OWNER_ID = "__system__"


def admin_owner_id() -> str:
    """Owner id used to attribute pre-multi-tenant IM rows: the built-in admin, else sentinel."""
    admin = get_builtin_admin()
    return admin.id if admin else SYSTEM_OWNER_ID


def set_role(user_id: str, role: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin" and role != "built_in_admin":
        raise PermissionError("built-in admin cannot be demoted")
    _update_field(user_id, "role", role)


def set_profile(user_id: str, name: str | None = None, email: str | None = None) -> None:
    """Update a user's editable profile fields (name and/or email).

    Email must stay unique across users; reusing another user's email raises ValueError.
    Passing None for a field leaves it unchanged.
    """
    if email is not None:
        existing = get_by_email(email)
        if existing is not None and existing.id != user_id:
            raise ValueError("email already in use")
    if name is not None:
        _update_field(user_id, "name", name)
    if email is not None:
        _update_field(user_id, "email", email)


def set_status(user_id: str, status: str) -> None:
    _update_field(user_id, "status", status)


def set_password(user_id: str, password_hash: str, must_reset: bool = False) -> None:
    with _db().transaction() as conn:
        conn.execute(
            "UPDATE users SET password_hash = :ph, must_reset = :mr WHERE id = :id",
            {"ph": password_hash, "mr": int(must_reset), "id": user_id},
        )


def set_must_reset(user_id: str, must_reset: bool) -> None:
    _update_field(user_id, "must_reset", int(must_reset))


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
    with _db().transaction() as conn:
        conn.execute("DELETE FROM users WHERE id = :id", {"id": user_id})


def _guard_not_builtin_admin(user_id: str, op: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin":
        raise PermissionError(f"built-in admin cannot be {op}d")


def _update_field(user_id: str, column: str, value: object) -> None:
    with _db().transaction() as conn:
        conn.execute(
            f"UPDATE users SET {column} = :val WHERE id = :id", {"val": value, "id": user_id}
        )


def get_or_create_im_user(owner_id: str, platform: str, platform_user_id: str) -> "User":
    from fleetent.platform import im_gateway_management as im

    return im.get_or_create(owner_id, platform, platform_user_id)


def _row_to_user(row: dict) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        api_key=row["api_key"],
        created_at=row["created_at"],
        email=row["email"],
        role=row["role"],
        status=row["status"],
        must_reset=row["must_reset"],
        password_hash=row["password_hash"],
        tenant_id=row["tenant_id"],
    )


def _init_db() -> None:
    # users table is now managed by Alembic (migration 068+).
    # Deployments must run `alembic upgrade head` before starting the application.
    pass
