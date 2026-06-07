"""change approvals.id from INTEGER to TEXT

Revision ID: 060
Revises: 059
Create Date: 2026-06-07

Owner module: governance/permission_gate

The runtime generates approval IDs as str(uuid.uuid4())[:8] (8-char hex
string), but the original schema created approvals.id as INTEGER. This
causes a datatype mismatch when the runtime tries to INSERT a text id.
Change the column to TEXT to match the runtime's UUID string format.
"""

import sqlalchemy as sa
from alembic import op


revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("approvals") as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.Integer(),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("approvals") as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.Text(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
