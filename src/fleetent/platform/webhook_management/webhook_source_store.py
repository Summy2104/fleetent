"""Platform-side managed webhook source store (live-webhooks).

Owns the management-DB ``webhook_sources`` table. All SQL goes through the unified
``fleetent.db`` boundary with named parameters; the HMAC shared secret is stored as Fernet
ciphertext via ``fleetent.secret_crypto`` and decrypted only when read for verification.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.secret_crypto import decrypt_text, encrypt_text


@dataclass(frozen=True)
class StoredWebhookSource:
    """A managed webhook source row (secret decrypted on read)."""

    id: str
    agent_id: int | None
    user_id: str
    message_template: str | None
    reply_target: str | None
    enabled: bool
    secret: str | None


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _row_to_source(row: object) -> StoredWebhookSource:
    secret_ct = row["secret_ciphertext"]  # type: ignore[index]
    agent_id = row["agent_id"]  # type: ignore[index]
    return StoredWebhookSource(
        id=str(row["id"]),  # type: ignore[index]
        agent_id=int(agent_id) if agent_id is not None else None,
        user_id=str(row["user_id"]),  # type: ignore[index]
        message_template=row["message_template"],  # type: ignore[index]
        reply_target=row["reply_target"],  # type: ignore[index]
        enabled=bool(row["enabled"]),  # type: ignore[index]
        secret=decrypt_text(str(secret_ct)) if secret_ct is not None else None,
    )


def put_source(
    *,
    id: str,
    user_id: str,
    agent_id: int | None = None,
    message_template: str | None = None,
    reply_target: str | None = None,
    enabled: bool = True,
    secret: str | None = None,
) -> None:
    """Insert or replace a webhook source. ``secret`` (if given) is stored as ciphertext."""
    now = _now_iso()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO webhook_sources
                (id, agent_id, user_id, message_template, reply_target,
                 enabled, secret_ciphertext, created_at, updated_at)
            VALUES
                (:id, :agent_id, :user_id, :message_template, :reply_target,
                 :enabled, :secret_ct, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                agent_id = excluded.agent_id,
                user_id = excluded.user_id,
                message_template = excluded.message_template,
                reply_target = excluded.reply_target,
                enabled = excluded.enabled,
                secret_ciphertext = excluded.secret_ciphertext,
                updated_at = excluded.updated_at
            """,
            {
                "id": id,
                "agent_id": agent_id,
                "user_id": user_id,
                "message_template": message_template,
                "reply_target": reply_target,
                "enabled": 1 if enabled else 0,
                "secret_ct": encrypt_text(secret) if secret is not None else None,
                "created_at": now,
                "updated_at": now,
            },
        )


def get_source(id: str) -> StoredWebhookSource | None:
    row = (
        _database()
        .execute(
            """
            SELECT id, agent_id, user_id, message_template, reply_target,
                   enabled, secret_ciphertext
            FROM webhook_sources WHERE id = :id
            """,
            {"id": id},
        )
        .fetchone()
    )
    return _row_to_source(row) if row is not None else None


def list_sources() -> list[StoredWebhookSource]:
    rows = (
        _database()
        .execute(
            """
            SELECT id, agent_id, user_id, message_template, reply_target,
                   enabled, secret_ciphertext
            FROM webhook_sources ORDER BY id
            """,
            {},
        )
        .fetchall()
    )
    return [_row_to_source(r) for r in rows]


def delete_source(id: str) -> None:
    with _database().transaction() as conn:
        conn.execute("DELETE FROM webhook_sources WHERE id = :id", {"id": id})
