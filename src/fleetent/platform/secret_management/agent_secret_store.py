"""Encrypted persistence for inject-mode credential values.

db runtime + named params, no ORM. Values are encrypted at rest with a symmetric key
read from the ``FLEETENT_SECRET_KEY`` process env (a urlsafe-base64 Fernet key) — the
platform never persists plaintext and depends on no external KMS. operator-mode slots
store nothing here; their values live only in the deployment host's ``.env``.
"""

import datetime
import os

from cryptography.fernet import Fernet, InvalidToken

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

SECRET_KEY_ENV = "FLEETENT_SECRET_KEY"


class SecretKeyError(RuntimeError):
    """Raised when ``FLEETENT_SECRET_KEY`` is missing or invalid for an inject operation."""


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _fernet() -> Fernet:
    key = os.environ.get(SECRET_KEY_ENV)
    if not key:
        raise SecretKeyError(
            f"{SECRET_KEY_ENV} not set; required to read/write inject-mode secrets"
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SecretKeyError(f"{SECRET_KEY_ENV} is not a valid Fernet key") from exc


def set_secret(agent_id: int, env_name: str, plaintext: str, updated_by: str | None = None) -> None:
    """Encrypt and upsert a credential value. Empty values are rejected (use delete)."""
    if not plaintext:
        raise ValueError("secret value must not be empty; use delete_secret to clear")
    ciphertext = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    _database().execute(
        "INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by) "
        "VALUES (:agent_id, :env_name, :ciphertext, :updated_at, :updated_by) "
        "ON CONFLICT(agent_id, env_name) DO UPDATE SET "
        "ciphertext = :ciphertext, updated_at = :updated_at, updated_by = :updated_by",
        {
            "agent_id": agent_id,
            "env_name": env_name,
            "ciphertext": ciphertext,
            "updated_at": _now(),
            "updated_by": updated_by,
        },
    )


def get_decrypted(agent_id: int, env_name: str) -> str | None:
    """Return the decrypted value, or None if no value is stored for this slot."""
    row = (
        _database()
        .execute(
            "SELECT ciphertext FROM agent_secrets "
            "WHERE agent_id = :agent_id AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    if row is None:
        return None
    try:
        return _fernet().decrypt(str(row["ciphertext"]).encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretKeyError(
            f"cannot decrypt {env_name} for agent {agent_id}; key rotated or ciphertext corrupt"
        ) from exc


def status(agent_id: int, env_name: str) -> str:
    """Return 'set' or 'unset' — never the value."""
    row = (
        _database()
        .execute(
            "SELECT 1 FROM agent_secrets WHERE agent_id = :agent_id AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    return "set" if row is not None else "unset"


def list_status(agent_id: int) -> dict[str, str]:
    """Map of env_name -> 'set' for every stored value of this agent."""
    rows = (
        _database()
        .execute(
            "SELECT env_name FROM agent_secrets WHERE agent_id = :agent_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return {str(r["env_name"]): "set" for r in rows}


def delete_secret(agent_id: int, env_name: str) -> None:
    _database().execute(
        "DELETE FROM agent_secrets WHERE agent_id = :agent_id AND env_name = :env_name",
        {"agent_id": agent_id, "env_name": env_name},
    )
