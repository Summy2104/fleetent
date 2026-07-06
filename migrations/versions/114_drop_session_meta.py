"""drop session_meta

Revision ID: 114
Revises: 113
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "114"
down_revision = "113"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(item["name"] == index for item in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if _has_table("session_meta") and _has_index("session_meta", "idx_session_meta_origin"):
        op.drop_index("idx_session_meta_origin", table_name="session_meta")
    if _has_table("session_meta"):
        op.drop_table("session_meta")


def downgrade() -> None:
    if not _has_table("session_meta"):
        op.create_table(
            "session_meta",
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("origin", sa.Text(), nullable=False, server_default="web"),
            sa.Column("status", sa.Text(), nullable=False, server_default="active"),
            sa.Column("takeover_actor", sa.Text(), nullable=True),
            sa.Column("takeover_at", sa.Text(), nullable=True),
            sa.Column("pinned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pin_note", sa.Text(), nullable=True),
            sa.Column(
                "agent_id",
                sa.Integer(),
                sa.ForeignKey("agents.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("user_id", sa.Text(), nullable=True),
            sa.Column("channel", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("session_id"),
        )
    if not _has_index("session_meta", "idx_session_meta_origin"):
        op.create_index("idx_session_meta_origin", "session_meta", ["origin", "status"])
