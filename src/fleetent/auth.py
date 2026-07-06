"""Authentication: password hashing, login sessions, role guard, built-in admin seed.

Password hashing uses stdlib scrypt (no external dependency). Login sessions are
in-process (single-instance); multi-instance clustering is out of scope here.
"""

import hashlib
import hmac
import os
import secrets
import time
from typing import Any, cast

from fleetent import user_store

BUILTIN_ADMIN_NAME = "admin"
# Fixed default credentials for on-prem first run. INSECURE — change after deploy.
BUILTIN_ADMIN_PASSWORD = "admin"

# Login sessions: token -> {"user_id": str, "last_active": float}
_SESSIONS: dict[str, dict[str, Any]] = {}

# scrypt cost parameters
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def _clock() -> float:
    return time.time()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    dk = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return hmac.compare_digest(dk.hex(), hash_hex)


def seed_builtin_admin() -> tuple[user_store.User, str] | None:
    """Create the bootstrap admin when no active admin exists.

    Returns (user, temp_password) when seeded, otherwise None.
    """
    if user_store.count_active_admins() > 0:
        # The forced reset is asserted once, at first seed below. We deliberately do NOT
        # re-assert it on later startups: re-forcing whenever the password was still the
        # bootstrap default trapped operators in a reset-every-restart loop, because
        # change-password accepts the default value and immediately re-armed the guard.
        return None
    temp_password = BUILTIN_ADMIN_PASSWORD
    user, _ = user_store.create_user(name=BUILTIN_ADMIN_NAME, email=None)
    user_store.set_role(user.id, "admin")
    # admin/admin is an insecure bootstrap credential: force a password change on first login.
    user_store.set_password(user.id, hash_password(temp_password), must_reset=True)
    refreshed = user_store.get_by_id(user.id)
    assert refreshed is not None
    return refreshed, temp_password


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {"user_id": user_id, "last_active": _clock()}
    return token


def validate_session(token: str, idle_timeout: float) -> str | None:
    """Return the session's user_id, or None if missing/idle-expired. Refreshes activity."""
    session = _SESSIONS.get(token)
    if session is None:
        return None
    if _clock() - session["last_active"] > idle_timeout:
        _SESSIONS.pop(token, None)
        return None
    session["last_active"] = _clock()
    return cast(str, session["user_id"])


def logout(token: str) -> None:
    _SESSIONS.pop(token, None)


def has_role(user: user_store.User | None, allowed: set[str]) -> bool:
    return user is not None and user.role in allowed


def require_role(user: user_store.User | None, allowed: set[str]) -> None:
    if not has_role(user, allowed):
        raise PermissionError("insufficient role")
