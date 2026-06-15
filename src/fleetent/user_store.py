"""SQLite-backed user store. Users authenticate via the api_keys table (hashed)."""

import datetime
import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fleetent import paths

# Kept for test legacy-shim and module-boundary detection; not used as a DB entry point
# after retire-raw-sqlite-connect (all connections go through db.py boundary).
DB_PATH = paths.data_dir() / "management.db"


def _hash_key(plaintext: str) -> str:
    """SHA-256 hash of a plaintext API key — single canonical source shared with api_key_store."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


# Injectable hook for resolving api_keys table entries.
# Platform startup wires this to api_key_store.resolve; standalone agents leave it None,
# falling back to the local api_keys hash lookup (no platform import needed).
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
    created_at: str
    email: str | None = None
    role: str = "viewer"
    status: str = "active"
    must_reset: int = 0
    password_hash: str | None = None
    tenant_id: str = "default"


_FULL_COLS = "id, name, created_at, email, role, status, must_reset, password_hash, tenant_id"


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


def create_user(
    name: str, email: str | None = None, tenant_id: str = "default"
) -> tuple["User", str]:
    """Create a new user and issue an API key.

    Returns (User, plaintext_key).  The plaintext is shown once and never persisted;
    the api_keys table stores only the SHA-256 hash.
    """
    plaintext = f"ma-{secrets.token_hex(32)}"
    now = datetime.datetime.now(datetime.UTC).isoformat()
    user_id = str(uuid.uuid4())
    db = _db()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users (id, name, created_at, email, tenant_id)"
            " VALUES (:id, :name, :created_at, :email, :tenant_id)",
            {
                "id": user_id,
                "name": name,
                "created_at": now,
                "email": email,
                "tenant_id": tenant_id,
            },
        )
        conn.execute(
            "INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at, call_count)"
            " VALUES (:user_id, :key_hash, :prefix, :scope, :created_at, 0)",
            {
                "user_id": user_id,
                "key_hash": _hash_key(plaintext),
                "prefix": plaintext[:11],
                "scope": json.dumps(["*"]),
                "created_at": now,
            },
        )
    result = get_by_id(user_id)
    assert result is not None
    return result, plaintext


def authenticate(plaintext: str) -> tuple[User, dict[str, Any]] | None:
    """Resolve a plaintext API key to (User, key_metadata).

    When the platform resolver is injected (set_api_key_resolver called at startup),
    delegates to it. Otherwise queries api_keys by hash — the single canonical path
    for standalone agents. Returns None when the key is invalid/revoked/expired or the
    owning user is blocked.
    """
    if _api_key_resolver is not None:
        meta = _api_key_resolver(plaintext)
        if meta is None:
            return None
        user = get_by_id(meta["user_id"])
        if user is None or user.status == "blocked":
            return None
        return user, meta

    # Standalone: query api_keys by hash (same table, no platform import needed).
    key_hash = _hash_key(plaintext)
    row = (
        _db()
        .execute(
            "SELECT id, user_id, scope, revoked_at, expires_at FROM api_keys WHERE key_hash = :kh",
            {"kh": key_hash},
        )
        .fetchone()
    )
    if row is None:
        return None
    if row["revoked_at"] is not None:
        return None
    if (
        row["expires_at"] is not None
        and row["expires_at"] <= datetime.datetime.now(datetime.UTC).isoformat()
    ):
        return None
    user = get_by_id(row["user_id"])
    if user is None or user.status == "blocked":
        return None
    scope = json.loads(row["scope"]) if row["scope"] else ["*"]
    return user, {
        "id": row["id"],
        "user_id": row["user_id"],
        "scope": scope,
        "prefix": plaintext[:11],
    }


def get_by_api_key(api_key: str) -> User | None:
    """Look up a user by API key (delegates to authenticate). Returns None if invalid."""
    result = authenticate(api_key)
    return result[0] if result else None


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


def rotate_key(user_id: str) -> tuple["User", str]:
    """Revoke all active api_keys for user_id and issue a new one.  Raises KeyError if not found.

    Returns (User, plaintext_key).  The plaintext is shown once and never persisted.
    """
    user = get_by_id(user_id)
    if user is None:
        raise KeyError(f"User not found: {user_id}")
    now = datetime.datetime.now(datetime.UTC).isoformat()
    plaintext = f"ma-{secrets.token_hex(32)}"
    with _db().transaction() as conn:
        conn.execute(
            "UPDATE api_keys SET revoked_at = :now WHERE user_id = :uid AND revoked_at IS NULL",
            {"now": now, "uid": user_id},
        )
        conn.execute(
            "INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at, call_count)"
            " VALUES (:user_id, :key_hash, :prefix, :scope, :created_at, 0)",
            {
                "user_id": user_id,
                "key_hash": _hash_key(plaintext),
                "prefix": plaintext[:11],
                "scope": json.dumps(["*"]),
                "created_at": now,
            },
        )
    return user, plaintext


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


def get_or_create_service_principal(agent_id: int) -> str:
    """Return the service-principal user id for an agent, creating the row if absent.

    Uses id=``agent:<agent_id>``, role=``service``. No api_key is issued — service
    principals authenticate only via credential resolution, never via inbound ma- keys.
    Idempotent: safe to call on every dispatch, not just on first bind.
    """
    principal_id = f"agent:{agent_id}"
    now = datetime.datetime.now(datetime.UTC).isoformat()
    db = _db()
    with db.transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE id = :id", {"id": principal_id}
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (id, name, created_at, role, tenant_id)"
                " VALUES (:id, :name, :created_at, :role, :tenant_id)",
                {
                    "id": principal_id,
                    "name": principal_id,
                    "created_at": now,
                    "role": "service",
                    "tenant_id": "default",
                },
            )
    return principal_id


def set_role(user_id: str, role: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin" and role != "built_in_admin":
        raise PermissionError("built-in admin cannot be demoted")
    if current is not None and current.role == "service":
        raise PermissionError(f"service principal {user_id!r} cannot be assigned a human role")
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
    user, _ = create_user(name=name, email=normalized)
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
    _guard_not_tenancy_approver(user_id)
    with _db().transaction() as conn:
        conn.execute("DELETE FROM users WHERE id = :id", {"id": user_id})


def _guard_not_builtin_admin(user_id: str, op: str) -> None:
    current = get_by_id(user_id)
    if current is not None and current.role == "built_in_admin":
        raise PermissionError(f"built-in admin cannot be {op}d")


def _guard_not_tenancy_approver(user_id: str) -> None:
    tenant_row = (
        _db()
        .execute(
            "SELECT id FROM tenants WHERE approver_user_id = :user_id ORDER BY id LIMIT 1",
            {"user_id": user_id},
        )
        .fetchone()
    )
    if tenant_row is not None:
        raise PermissionError(f"user is tenant approver for tenant {tenant_row['id']!r}")

    team_row = (
        _db()
        .execute(
            "SELECT id FROM teams WHERE approver_user_id = :user_id ORDER BY id LIMIT 1",
            {"user_id": user_id},
        )
        .fetchone()
    )
    if team_row is not None:
        raise PermissionError(f"user is team approver for team {team_row['id']!r}")


def _update_field(user_id: str, column: str, value: object) -> None:
    with _db().transaction() as conn:
        conn.execute(
            f"UPDATE users SET {column} = :val WHERE id = :id", {"val": value, "id": user_id}
        )


def _row_to_user(row: dict) -> User:
    return User(
        id=row["id"],
        name=row["name"],
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
