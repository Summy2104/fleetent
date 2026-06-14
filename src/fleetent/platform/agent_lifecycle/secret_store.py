"""Encrypted per-agent secret value store for materialization inject mode."""

from __future__ import annotations

import datetime
from typing import Literal

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.secret_crypto import (
    SecretKeyError as _SecretKeyError,
)
from fleetent.secret_crypto import (
    _fernet,
    decrypt_text,
    encrypt_text,
)

SecretStatus = Literal["set", "unset"]
SecretKeyError = _SecretKeyError


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def set(agent_id: int | None, env_name: str, plaintext: str, updated_by: str | None = None) -> None:
    """Encrypt and store a secret value for one slot.

    ``agent_id=None`` targets the shared (cross-agent) scope used by provider/connector keys.
    """
    if plaintext == "":
        raise ValueError("empty secret values are rejected; use delete to clear a value")
    ciphertext = encrypt_text(plaintext)
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by)
            VALUES (:agent_id, :env_name, :ciphertext, :updated_at, :updated_by)
            ON CONFLICT(COALESCE(agent_id, -1), env_name) DO UPDATE SET
                ciphertext = :ciphertext,
                updated_at = :updated_at,
                updated_by = :updated_by
            """,
            {
                "agent_id": agent_id,
                "env_name": env_name,
                "ciphertext": ciphertext,
                "updated_at": _now(),
                "updated_by": updated_by,
            },
        )


def get_decrypted(agent_id: int | None, env_name: str) -> str | None:
    """Return the decrypted value for this exact scope, or None when the slot is unset."""
    _fernet()
    row = (
        _database()
        .execute(
            "SELECT ciphertext FROM agent_secrets WHERE agent_id IS :agent_id "
            "AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    if row is None:
        return None
    return decrypt_text(str(row["ciphertext"]))


def get_resolved(agent_id: int, env_name: str) -> str | None:
    """Resolve a slot value, preferring the per-agent scope then the shared scope."""
    return get_decrypted(agent_id, env_name) or get_decrypted(None, env_name)


def status(agent_id: int | None, env_name: str) -> SecretStatus:
    """Return only whether a value exists; never expose plaintext or ciphertext."""
    row = (
        _database()
        .execute(
            "SELECT 1 FROM agent_secrets WHERE agent_id IS :agent_id AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    return "set" if row is not None else "unset"


def delete(agent_id: int | None, env_name: str) -> None:
    """Delete an injected secret value. Missing rows are a no-op."""
    _database().execute(
        "DELETE FROM agent_secrets WHERE agent_id IS :agent_id AND env_name = :env_name",
        {"agent_id": agent_id, "env_name": env_name},
    )
