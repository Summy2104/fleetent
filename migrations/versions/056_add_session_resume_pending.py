"""add resume_pending flag to session_meta

Revision ID: 056
Revises: 055
Create Date: 2026-06-06

Owner module: platform / chat-management / session-restart-recovery

Marks sessions that were active just before an agent restart so the next request
can be recognized as a resumed (interrupted) conversation.
"""

import sqlalchemy as sa
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.add_column(
            sa.Column("resume_pending", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.drop_column("resume_pending")
