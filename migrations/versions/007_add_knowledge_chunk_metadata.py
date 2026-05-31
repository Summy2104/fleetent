"""add knowledge chunk metadata

Revision ID: 007
Revises: 006
Create Date: 2026-06-01

Owner module: knowledge-base
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "metadata_json")
