"""add kb_connectors.custom — free-form connector metadata

A JSON blob of admin-defined key/values attached to a KB source connector (mirrors
model_providers.params). Free-form: not filtered to the kind's schema and not fed
into the ingestion model — stored + surfaced as metadata. Nullable; legacy rows
default to an empty object in the store.

Revision ID: 052
Revises: 051
Create Date: 2026-06-05

Owner module: knowledge-base-management
"""

import sqlalchemy as sa
from alembic import op

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_connectors", sa.Column("custom", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("kb_connectors") as batch_op:
        batch_op.drop_column("custom")
