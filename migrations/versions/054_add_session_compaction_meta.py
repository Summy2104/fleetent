"""add compaction metadata columns to session_meta

Revision ID: 054
Revises: 053
Create Date: 2026-06-06

Owner module: platform / chat-management / session-compaction-checkpoint

Records the last compaction event per session so the admin console can surface
compression history without reading transcript files.
"""

import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.add_column(sa.Column("last_compaction_at", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("messages_before_compaction", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("messages_after_compaction", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("compaction_summary_preview", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.drop_column("compaction_summary_preview")
        batch_op.drop_column("messages_after_compaction")
        batch_op.drop_column("messages_before_compaction")
        batch_op.drop_column("last_compaction_at")
