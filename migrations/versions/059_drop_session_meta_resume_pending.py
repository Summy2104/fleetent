"""drop resume_pending column from session_meta

Revision ID: 059
Revises: 058
Create Date: 2026-06-07

Owner module: platform / chat-management

resume_pending migrated to an agent-side .resume marker file (Agent/Platform
decoupling). The platform session_meta column no longer has a writer.
"""

import sqlalchemy as sa
from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.drop_column("resume_pending")


def downgrade() -> None:
    with op.batch_alter_table("session_meta") as batch_op:
        batch_op.add_column(
            sa.Column("resume_pending", sa.Integer(), nullable=False, server_default="0")
        )
