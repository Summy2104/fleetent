"""Authentication: password hashing, login sessions, role guard, built-in admin seed.

Password hashing uses stdlib scrypt (no external dependency). Login sessions are
in-process (single-instance); multi-instance clustering is out of scope here.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time

from fleetent import user_store

BUILTIN_ADMIN_NAME = "admin"

# Login sessions: token -> {"user_id": str, "last_active": float}
_SESSIONS: dict[str, dict] = {}

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
    """Create the built-in admin on first run. Returns (user, temp_password) or None.

    Returns None (no-op) if a built-in admin already exists.
    """
    if user_store.get_builtin_admin() is not None:
        return None
    temp_password = secrets.token_urlsafe(12)
    user = user_store.create_user(name=BUILTIN_ADMIN_NAME, email=None)
    user_store.set_role(user.id, "built_in_admin")
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
    return session["user_id"]


def logout(token: str) -> None:
    _SESSIONS.pop(token, None)


def generate_totp_secret() -> str:
    """Return a new base32 TOTP secret."""
    return base64.b32encode(os.urandom(20)).decode()


def totp(secret: str, t: float | None = None, step: int = 30, digits: int = 6) -> str:
    """Compute the RFC 6238 TOTP code for a base32 secret."""
    if t is None:
        t = time.time()
    counter = int(t) // step
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def verify_totp(secret: str, code: str, t: float | None = None, window: int = 1) -> bool:
    """Verify a TOTP code, tolerating +/- `window` steps for clock skew."""
    if t is None:
        t = time.time()
    return any(totp(secret, t + offset * 30) == code for offset in range(-window, window + 1))


def enable_2fa(user_id: str) -> str:
    """Generate and store a TOTP secret for the user; returns the secret."""
    secret = generate_totp_secret()
    user_store.set_totp_secret(user_id, secret)
    return secret


def verify_user_2fa(user_id: str, code: str, t: float | None = None) -> bool:
    user = user_store.get_by_id(user_id)
    if user is None or not user.totp_secret:
        return False
    return verify_totp(user.totp_secret, code, t=t)


def has_role(user: user_store.User | None, allowed: set[str]) -> bool:
    return user is not None and user.role in allowed


def require_role(user: user_store.User | None, allowed: set[str]) -> None:
    if not has_role(user, allowed):
        raise PermissionError("insufficient role")
