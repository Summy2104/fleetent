"""drop runtime-coupling columns from session_meta

Revision ID: 058
Revises: 057
Create Date: 2026-06-07

Owner module: platform / chat-management

Removes agent-runtime data that was wrongly written into the platform session_meta
table (Agent/Platform decoupling). token usage and compaction stats are already
recorded in observability traces; these columns had no remaining writer.
"""

import sqlalchemy as sa
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

_DROPPED = (
    "total_input_tokens",
    "total_output_tokens",
    "last_compaction_at",
    "messages_before_compaction",
    "messages_after_compaction",
    "compaction_summary_preview",
)


def upgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        for col in _DROPPED:
            batch_op.drop_column(col)


def downgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.add_column(sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("last_compaction_at", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("messages_before_compaction", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("messages_after_compaction", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("compaction_summary_preview", sa.Text(), nullable=True))
