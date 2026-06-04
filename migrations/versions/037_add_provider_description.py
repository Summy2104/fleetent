"""add provider description field

Revision ID: 037
Revises: 036
Create Date: 2026-06-04

Owner module: platform / model-provider-management
"""

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_providers",
        sa.Column("description", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("model_providers", "description")