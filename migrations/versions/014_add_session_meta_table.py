"""add session_meta table

Revision ID: 014
Revises: 013
Create Date: 2026-06-02

Owner module: platform / chat-management

Session message transcripts stay in session_mgr's JSON files. Only the management
metadata (origin / status / takeover / pinned) is persisted here so the admin console
can list, govern, and isolate playground sessions without touching transcript storage.
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_meta",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False, server_default="web"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("takeover_actor", sa.Text(), nullable=True),
        sa.Column("takeover_at", sa.Text(), nullable=True),
        sa.Column("pinned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pin_note", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("idx_session_meta_origin", "session_meta", ["origin", "status"])


def downgrade() -> None:
    op.drop_index("idx_session_meta_origin", table_name="session_meta")
    op.drop_table("session_meta")
