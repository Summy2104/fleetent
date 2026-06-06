"""add token accumulation columns to session_meta

Revision ID: 055
Revises: 054
Create Date: 2026-06-06

Owner module: platform / chat-management / session-token-tracking

Per-session cumulative token usage so the admin console can surface cost/consumption
without scanning traces.
"""

import sqlalchemy as sa
from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.add_column(
            sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.drop_column("total_output_tokens")
        batch_op.drop_column("total_input_tokens")
