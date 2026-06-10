"""onboard api_keys / audit_log / im_connectors / im_channel_allowlist into alembic

Revision ID: 067
Revises: 066
Create Date: 2026-06-10

These four management tables have been created at runtime by each store's _init_db()
since the project started.  This migration brings them under alembic authority so the
management DB has a single schema owner.

CREATE TABLE IF NOT EXISTS is used so that:
- fresh databases: the migration creates the tables.
- already-deployed databases (tables already built by _init_db): no-op, no data lost.

Column definitions are copied verbatim from each store's original _init_db() DDL.
"""

from alembic import op

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            id           INTEGER PRIMARY KEY,
            user_id      TEXT NOT NULL,
            key_hash     TEXT UNIQUE NOT NULL,
            prefix       TEXT NOT NULL,
            scope        TEXT NOT NULL DEFAULT '["*"]',
            note         TEXT,
            expires_at   TEXT,
            revoked_at   TEXT,
            created_at   TEXT NOT NULL,
            last_used_at TEXT,
            last_ip      TEXT,
            last_ua      TEXT,
            call_count   INTEGER NOT NULL DEFAULT 0
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id            INTEGER PRIMARY KEY,
            actor_user_id TEXT,
            action        TEXT NOT NULL,
            target_type   TEXT,
            target_id     TEXT,
            detail        TEXT,
            batch_id      TEXT,
            created_at    TEXT NOT NULL
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS im_connectors (
            id                 INTEGER PRIMARY KEY,
            owner_id           TEXT NOT NULL,
            platform           TEXT NOT NULL,
            enabled            INTEGER NOT NULL DEFAULT 0,
            allowlist_enforced INTEGER NOT NULL DEFAULT 0,
            config             TEXT,
            status             TEXT NOT NULL DEFAULT 'stopped',
            last_heartbeat_at  TEXT,
            last_error         TEXT,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL,
            UNIQUE(owner_id, platform)
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS im_channel_allowlist (
            id         INTEGER PRIMARY KEY,
            owner_id   TEXT NOT NULL,
            platform   TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id   TEXT NOT NULL,
            allowed    INTEGER NOT NULL DEFAULT 1,
            note       TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(owner_id, platform, scope_type, scope_id)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS im_channel_allowlist")
    op.execute("DROP TABLE IF EXISTS im_connectors")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS api_keys")
