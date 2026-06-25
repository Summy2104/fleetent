"""Standalone SQLite-backed per-user MCP token store (D7).

Implements :class:`~fleetent.integrations.mcp.per_user_tokens.UserTokenStore` against
the per-agent ``agent_state.db`` (``mcp_user_tokens`` table, created by the unified
AGENT_STATE_MIGRATIONS). Access and refresh tokens are stored as Fernet ciphertext via
the shared :mod:`fleetent.secret_crypto` helper — never in the clear — and isolated by
the ``(user_id, agent_id, server_id)`` triple.

The migrated DB handle is injected at construction (mirroring ``artifact_exchange`` /
``sub_agent_lifecycle``); all SQL goes through the unified :mod:`fleetent.db` boundary
with named parameters and no raw ``sqlite3.connect`` or ORM. No ``fleetent.platform.*``
import — this is standalone agent-side state.
"""

from __future__ import annotations

import datetime

from fleetent.db import SQLiteDatabase
from fleetent.integrations.mcp.per_user_tokens import UserToken
from fleetent.secret_crypto import decrypt_text, encrypt_text


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


class StandaloneUserTokenStore:
    """Encrypted, triple-keyed per-user token store over the per-agent state DB."""

    def __init__(self, db: SQLiteDatabase) -> None:
        """Bind the store to a migrated per-agent ``agent_state.db`` handle.

        Args:
            db: A SQLite handle whose schema is already migrated to include the
                ``mcp_user_tokens`` table (migrate-on-open is performed by the caller).
        """
        self._db = db

    def get(self, user_id: str, agent_id: str, server_id: str) -> UserToken | None:
        """Return the decrypted token for the triple, or None when none is stored."""
        row = self._db.execute(
            """
                SELECT access_token_ciphertext, refresh_token_ciphertext, expires_at, scope
                FROM mcp_user_tokens
                WHERE user_id = :user_id AND agent_id = :agent_id AND server_id = :server_id
                """,
            {"user_id": user_id, "agent_id": agent_id, "server_id": server_id},
        ).fetchone()
        if row is None:
            return None
        refresh_ct = row["refresh_token_ciphertext"]
        expires_at = row["expires_at"]
        return UserToken(
            access_token=decrypt_text(str(row["access_token_ciphertext"])),
            refresh_token=decrypt_text(str(refresh_ct)) if refresh_ct is not None else None,
            expires_at=float(expires_at) if expires_at is not None else None,
            scope=row["scope"],
        )

    def put(self, user_id: str, agent_id: str, server_id: str, token: UserToken) -> None:
        """Insert or overwrite the encrypted token for the triple."""
        now = _now()
        self._db.execute(
            """
            INSERT INTO mcp_user_tokens
                (user_id, agent_id, server_id, access_token_ciphertext,
                 refresh_token_ciphertext, expires_at, scope, created_at, updated_at)
            VALUES
                (:user_id, :agent_id, :server_id, :access_ct,
                 :refresh_ct, :expires_at, :scope, :created_at, :updated_at)
            ON CONFLICT(user_id, agent_id, server_id) DO UPDATE SET
                access_token_ciphertext = excluded.access_token_ciphertext,
                refresh_token_ciphertext = excluded.refresh_token_ciphertext,
                expires_at = excluded.expires_at,
                scope = excluded.scope,
                updated_at = excluded.updated_at
            """,
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "server_id": server_id,
                "access_ct": encrypt_text(token.access_token),
                "refresh_ct": (
                    encrypt_text(token.refresh_token) if token.refresh_token is not None else None
                ),
                "expires_at": token.expires_at,
                "scope": token.scope,
                "created_at": now,
                "updated_at": now,
            },
        )

    def delete(self, user_id: str, agent_id: str, server_id: str) -> None:
        """Remove any token for the triple; a no-op when none exists."""
        self._db.execute(
            """
            DELETE FROM mcp_user_tokens
            WHERE user_id = :user_id AND agent_id = :agent_id AND server_id = :server_id
            """,
            {"user_id": user_id, "agent_id": agent_id, "server_id": server_id},
        )
