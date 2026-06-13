"""Unify agent_admin_state and session_meta agent references to INTEGER foreign keys.

Revision ID: 083
Revises: 082
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _rebuild_agent_admin_state_upgrade() -> None:
    if not _has_table("agent_admin_state"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_admin_state__new (
            agent_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'enabled',
            provenance TEXT NOT NULL DEFAULT 'adhoc',
            drift INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (agent_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_admin_state__new
            (agent_id, status, provenance, drift, archived_at, updated_at)
        SELECT
            agents.id,
            agent_admin_state.status,
            agent_admin_state.provenance,
            agent_admin_state.drift,
            agent_admin_state.archived_at,
            agent_admin_state.updated_at
        FROM agent_admin_state
        JOIN agents ON agents.name = agent_admin_state.agent_name
        """
    )
    op.drop_table("agent_admin_state")
    op.rename_table("agent_admin_state__new", "agent_admin_state")


def _rebuild_session_meta_upgrade() -> None:
    if not _has_table("session_meta"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE session_meta__new (
            session_id TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'web',
            status TEXT NOT NULL DEFAULT 'active',
            takeover_actor TEXT,
            takeover_at TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            pin_note TEXT,
            agent_id INTEGER,
            user_id TEXT,
            channel TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO session_meta__new
            (session_id, origin, status, takeover_actor, takeover_at, pinned,
             pin_note, agent_id, user_id, channel, updated_at)
        SELECT
            session_meta.session_id,
            session_meta.origin,
            session_meta.status,
            session_meta.takeover_actor,
            session_meta.takeover_at,
            session_meta.pinned,
            session_meta.pin_note,
            agents.id,
            session_meta.user_id,
            session_meta.channel,
            session_meta.updated_at
        FROM session_meta
        LEFT JOIN agents ON agents.name = session_meta.agent_name
        WHERE session_meta.agent_name IS NULL OR agents.id IS NOT NULL
        """
    )
    op.drop_index("idx_session_meta_origin", table_name="session_meta")
    op.drop_table("session_meta")
    op.rename_table("session_meta__new", "session_meta")
    op.create_index("idx_session_meta_origin", "session_meta", ["origin", "status"])


def _rebuild_session_meta_downgrade() -> None:
    if not _has_table("session_meta"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE session_meta__old (
            session_id TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'web',
            status TEXT NOT NULL DEFAULT 'active',
            takeover_actor TEXT,
            takeover_at TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            pin_note TEXT,
            agent_name TEXT,
            user_id TEXT,
            channel TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO session_meta__old
            (session_id, origin, status, takeover_actor, takeover_at, pinned,
             pin_note, agent_name, user_id, channel, updated_at)
        SELECT
            session_meta.session_id,
            session_meta.origin,
            session_meta.status,
            session_meta.takeover_actor,
            session_meta.takeover_at,
            session_meta.pinned,
            session_meta.pin_note,
            agents.name,
            session_meta.user_id,
            session_meta.channel,
            session_meta.updated_at
        FROM session_meta
        LEFT JOIN agents ON agents.id = session_meta.agent_id
        """
    )
    op.drop_index("idx_session_meta_origin", table_name="session_meta")
    op.drop_table("session_meta")
    op.rename_table("session_meta__old", "session_meta")
    op.create_index("idx_session_meta_origin", "session_meta", ["origin", "status"])


def _rebuild_agent_admin_state_downgrade() -> None:
    if not _has_table("agent_admin_state"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_admin_state__old (
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'enabled',
            provenance TEXT NOT NULL DEFAULT 'adhoc',
            drift INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (agent_name)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_admin_state__old
            (agent_name, status, provenance, drift, archived_at, updated_at)
        SELECT
            agents.name,
            agent_admin_state.status,
            agent_admin_state.provenance,
            agent_admin_state.drift,
            agent_admin_state.archived_at,
            agent_admin_state.updated_at
        FROM agent_admin_state
        JOIN agents ON agents.id = agent_admin_state.agent_id
        """
    )
    op.drop_table("agent_admin_state")
    op.rename_table("agent_admin_state__old", "agent_admin_state")


def upgrade() -> None:
    _rebuild_agent_admin_state_upgrade()
    _rebuild_session_meta_upgrade()


def downgrade() -> None:
    _rebuild_session_meta_downgrade()
    _rebuild_agent_admin_state_downgrade()
