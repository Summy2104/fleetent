"""Encrypted per-user external credentials."""

from __future__ import annotations

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.secret_crypto import decrypt_text, encrypt_text


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    expires_at = normalized.get("expires_at")
    expires_in = normalized.get("expires_in")
    if expires_at is None and isinstance(expires_in, (int, float)):
        normalized["expires_at"] = (
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=int(expires_in))
        ).isoformat()
    return normalized


def put_oauth_credential(
    user_id: str,
    service_id: str,
    payload: dict[str, Any],
    *,
    updated_by: str | None = None,
    status: str = "authorized",
) -> None:
    ciphertext = encrypt_text(json.dumps(_normalize_payload(payload), separators=(",", ":")))
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO external_credentials
                (user_id, service_id, payload_ciphertext, status, updated_at, updated_by)
            VALUES
                (:user_id, :service_id, :payload_ciphertext, :status, :updated_at, :updated_by)
            ON CONFLICT(user_id, service_id) DO UPDATE SET
                payload_ciphertext = excluded.payload_ciphertext,
                status = excluded.status,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            {
                "user_id": user_id,
                "service_id": service_id,
                "payload_ciphertext": ciphertext,
                "status": status,
                "updated_at": _now(),
                "updated_by": updated_by,
            },
        )


def put_apikey_credential(
    user_id: str,
    service_id: str,
    api_key: str,
    *,
    updated_by: str | None = None,
) -> None:
    """Store a user-submitted API key as an authorized credential.

    The payload form is ``{"api_key": <value>}``; the value is encrypted at rest by
    the shared crypto helper. API keys have no refresh concept, so the status is
    always ``authorized`` until the user re-submits or it is revoked.
    """
    put_oauth_credential(
        user_id,
        service_id,
        {"api_key": api_key},
        updated_by=updated_by,
        status="authorized",
    )


def delete_credential(user_id: str, service_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            DELETE FROM external_credentials
            WHERE user_id = :user_id AND service_id = :service_id
            """,
            {"user_id": user_id, "service_id": service_id},
        )


def delete_all_credentials_for_user(user_id: str) -> None:
    """Delete all stored credentials for a user (e.g. service-principal cleanup on agent delete)."""
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM external_credentials WHERE user_id = :user_id",
            {"user_id": user_id},
        )


def list_all_credentials() -> list[dict[str, Any]]:
    """Return all credentials metadata (no payload) for the admin authorization matrix."""
    rows = (
        _database()
        .execute("SELECT user_id, service_id, status, updated_at FROM external_credentials")
        .fetchall()
    )
    return [
        {
            "user_id": str(row["user_id"]),
            "service_id": str(row["service_id"]),
            "status": str(row["status"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def list_credentials_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return all credentials metadata for a user (no payload), used for offboarding."""
    rows = (
        _database()
        .execute(
            """
            SELECT service_id, status, updated_at
            FROM external_credentials
            WHERE user_id = :user_id
            """,
            {"user_id": user_id},
        )
        .fetchall()
    )
    return [
        {
            "service_id": str(row["service_id"]),
            "status": str(row["status"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def count_credentials_by_status(service_id: str) -> dict[str, int]:
    """Return credential counts grouped by status for a service, used for lifecycle stats."""
    rows = (
        _database()
        .execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM external_credentials
            WHERE service_id = :service_id
            GROUP BY status
            """,
            {"service_id": service_id},
        )
        .fetchall()
    )
    return {str(row["status"]): int(row["cnt"]) for row in rows}


def get_credential(user_id: str, service_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            """
            SELECT payload_ciphertext, status, updated_at, updated_by
            FROM external_credentials
            WHERE user_id = :user_id AND service_id = :service_id
            """,
            {"user_id": user_id, "service_id": service_id},
        )
        .fetchone()
    )
    if row is None:
        return None
    return {
        "user_id": user_id,
        "service_id": service_id,
        "payload": json.loads(decrypt_text(str(row["payload_ciphertext"]))),
        "status": str(row["status"]),
        "updated_at": str(row["updated_at"]),
        "updated_by": row["updated_by"],
    }
