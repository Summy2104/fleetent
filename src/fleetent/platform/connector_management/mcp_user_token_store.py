"""Platform-side per-user MCP OAuth token + pending-auth stores (managed slice 2).

Owns the management-DB ``mcp_user_tokens`` (triple-keyed, encrypted access/refresh tokens)
and ``mcp_oauth_pending`` (short-TTL, one-time PKCE/state registration) tables. All SQL goes
through the unified ``fleetent.db`` boundary with named parameters; access/refresh tokens and
the PKCE code_verifier are stored as Fernet ciphertext via ``fleetent.secret_crypto``. The
refresh token is held here and MUST NOT be returned out of platform.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.secret_crypto import decrypt_text, encrypt_text

# Pending authorizations are consumed within one browser round-trip; keep the window tight.
PENDING_TTL_SECONDS = 600.0


@dataclass(frozen=True)
class StoredToken:
    """A platform-stored per-user token (refresh_token stays internal to platform).

    Carries the OAuth config needed to refresh itself (token_url/client_id/
    client_secret_env) so refresh needs no registry round-trip.
    """

    access_token: str
    refresh_token: str | None
    expires_at: float | None
    scope: str | None
    token_url: str
    client_id: str
    client_secret_env: str


@dataclass(frozen=True)
class PendingAuth:
    """Reverse-resolved authorization context bound to a one-time ``state``."""

    code_verifier: str
    user_id: str
    agent_id: str
    server_id: str
    token_url: str
    client_id: str
    client_secret_env: str
    redirect_uri: str


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def put_token(
    user_id: str,
    agent_id: str,
    server_id: str,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_at: float | None,
    scope: str | None,
    token_url: str = "",
    client_id: str = "",
    client_secret_env: str = "",
) -> None:
    now = _now_iso()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_user_tokens
                (user_id, agent_id, server_id, access_token_ciphertext,
                 refresh_token_ciphertext, expires_at, scope,
                 token_url, client_id, client_secret_env, created_at, updated_at)
            VALUES
                (:user_id, :agent_id, :server_id, :access_ct,
                 :refresh_ct, :expires_at, :scope,
                 :token_url, :client_id, :client_secret_env, :created_at, :updated_at)
            ON CONFLICT(user_id, agent_id, server_id) DO UPDATE SET
                access_token_ciphertext = excluded.access_token_ciphertext,
                refresh_token_ciphertext = excluded.refresh_token_ciphertext,
                expires_at = excluded.expires_at,
                scope = excluded.scope,
                token_url = excluded.token_url,
                client_id = excluded.client_id,
                client_secret_env = excluded.client_secret_env,
                updated_at = excluded.updated_at
            """,
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "server_id": server_id,
                "access_ct": encrypt_text(access_token),
                "refresh_ct": encrypt_text(refresh_token) if refresh_token is not None else None,
                "expires_at": expires_at,
                "scope": scope,
                "token_url": token_url,
                "client_id": client_id,
                "client_secret_env": client_secret_env,
                "created_at": now,
                "updated_at": now,
            },
        )


def get_token(user_id: str, agent_id: str, server_id: str) -> StoredToken | None:
    row = (
        _database()
        .execute(
            """
            SELECT access_token_ciphertext, refresh_token_ciphertext, expires_at, scope,
                   token_url, client_id, client_secret_env
            FROM mcp_user_tokens
            WHERE user_id = :user_id AND agent_id = :agent_id AND server_id = :server_id
            """,
            {"user_id": user_id, "agent_id": agent_id, "server_id": server_id},
        )
        .fetchone()
    )
    if row is None:
        return None
    refresh_ct = row["refresh_token_ciphertext"]
    expires_at = row["expires_at"]
    return StoredToken(
        access_token=decrypt_text(str(row["access_token_ciphertext"])),
        refresh_token=decrypt_text(str(refresh_ct)) if refresh_ct is not None else None,
        expires_at=float(expires_at) if expires_at is not None else None,
        scope=row["scope"],
        token_url=str(row["token_url"] or ""),
        client_id=str(row["client_id"] or ""),
        client_secret_env=str(row["client_secret_env"] or ""),
    )


def delete_token(user_id: str, agent_id: str, server_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            DELETE FROM mcp_user_tokens
            WHERE user_id = :user_id AND agent_id = :agent_id AND server_id = :server_id
            """,
            {"user_id": user_id, "agent_id": agent_id, "server_id": server_id},
        )


def put_pending(
    *,
    state: str,
    code_verifier: str,
    user_id: str,
    agent_id: str,
    server_id: str,
    token_url: str,
    client_id: str,
    client_secret_env: str,
    redirect_uri: str,
    now: float,
) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_oauth_pending
                (state, code_verifier_ciphertext, user_id, agent_id, server_id,
                 token_url, client_id, client_secret_env, redirect_uri, created_at_epoch, consumed)
            VALUES
                (:state, :verifier_ct, :user_id, :agent_id, :server_id,
                 :token_url, :client_id, :client_secret_env, :redirect_uri, :created_at_epoch, 0)
            ON CONFLICT(state) DO UPDATE SET
                code_verifier_ciphertext = excluded.code_verifier_ciphertext,
                user_id = excluded.user_id,
                agent_id = excluded.agent_id,
                server_id = excluded.server_id,
                token_url = excluded.token_url,
                client_id = excluded.client_id,
                client_secret_env = excluded.client_secret_env,
                redirect_uri = excluded.redirect_uri,
                created_at_epoch = excluded.created_at_epoch,
                consumed = 0
            """,
            {
                "state": state,
                "verifier_ct": encrypt_text(code_verifier),
                "user_id": user_id,
                "agent_id": agent_id,
                "server_id": server_id,
                "token_url": token_url,
                "client_id": client_id,
                "client_secret_env": client_secret_env,
                "redirect_uri": redirect_uri,
                "created_at_epoch": now,
            },
        )


def consume_pending(state: str, *, now: float) -> PendingAuth | None:
    """Atomically consume a pending-auth: one-time and within TTL, else None."""
    with _database().transaction() as conn:
        row = conn.execute(
            """
            SELECT code_verifier_ciphertext, user_id, agent_id, server_id, token_url,
                   client_id, client_secret_env, redirect_uri, created_at_epoch, consumed
            FROM mcp_oauth_pending WHERE state = :state
            """,
            {"state": state},
        ).fetchone()
        if row is None or int(row["consumed"]) != 0:
            return None
        if now - float(row["created_at_epoch"]) > PENDING_TTL_SECONDS:
            return None
        conn.execute(
            "UPDATE mcp_oauth_pending SET consumed = 1 WHERE state = :state",
            {"state": state},
        )
        return PendingAuth(
            code_verifier=decrypt_text(str(row["code_verifier_ciphertext"])),
            user_id=str(row["user_id"]),
            agent_id=str(row["agent_id"]),
            server_id=str(row["server_id"]),
            token_url=str(row["token_url"]),
            client_id=str(row["client_id"]),
            client_secret_env=str(row["client_secret_env"]),
            redirect_uri=str(row["redirect_uri"]),
        )
