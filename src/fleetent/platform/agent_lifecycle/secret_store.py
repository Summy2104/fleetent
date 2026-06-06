"""Encrypted per-agent secret value store for materialization inject mode."""

from __future__ import annotations

import datetime
import os
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

SecretStatus = Literal["set", "unset"]


class SecretKeyError(RuntimeError):
    """Raised when the platform secret-store master key is missing or invalid."""


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _fernet() -> Fernet:
    key = os.environ.get("FLEETENT_SECRET_KEY", "")
    if not key:
        raise SecretKeyError("FLEETENT_SECRET_KEY is required for inject secret operations")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise SecretKeyError("FLEETENT_SECRET_KEY must be a valid Fernet key") from exc


def set(agent_id: int, env_name: str, plaintext: str, updated_by: str | None = None) -> None:
    """Encrypt and store a secret value for one agent/env slot."""
    if plaintext == "":
        raise ValueError("empty secret values are rejected; use delete to clear a value")
    ciphertext = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by)
            VALUES (:agent_id, :env_name, :ciphertext, :updated_at, :updated_by)
            ON CONFLICT(agent_id, env_name) DO UPDATE SET
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


def get_decrypted(agent_id: int, env_name: str) -> str | None:
    """Return the decrypted value, or None when the slot is unset."""
    fernet = _fernet()
    row = (
        _database()
        .execute(
            "SELECT ciphertext FROM agent_secrets WHERE agent_id = :agent_id "
            "AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    if row is None:
        return None
    try:
        return fernet.decrypt(str(row["ciphertext"]).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretKeyError("FLEETENT_SECRET_KEY cannot decrypt the stored secret") from exc


def status(agent_id: int, env_name: str) -> SecretStatus:
    """Return only whether a value exists; never expose plaintext or ciphertext."""
    row = (
        _database()
        .execute(
            "SELECT 1 FROM agent_secrets WHERE agent_id = :agent_id AND env_name = :env_name",
            {"agent_id": agent_id, "env_name": env_name},
        )
        .fetchone()
    )
    return "set" if row is not None else "unset"


def delete(agent_id: int, env_name: str) -> None:
    """Delete an injected secret value. Missing rows are a no-op."""
    _database().execute(
        "DELETE FROM agent_secrets WHERE agent_id = :agent_id AND env_name = :env_name",
        {"agent_id": agent_id, "env_name": env_name},
    )
