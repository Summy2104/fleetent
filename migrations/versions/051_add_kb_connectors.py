"""add kb_connectors table — DB-managed knowledge-base source connectors

Lets the admin console manage Google Drive / Confluence ingestion connectors that
were previously config-file only. ``config`` is a JSON blob of the kind-specific
fields (folder_id/recursive, base_url/space_key/page_id…) plus env-reference names
for credentials (never raw secrets). tenant_id/kb_id scope the ingestion target.

Revision ID: 051
Revises: 050
Create Date: 2026-06-05

Owner module: knowledge-base-management
"""

import sqlalchemy as sa
from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_connectors",
        sa.Column("connector_id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),  # google_drive | confluence
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kb_connectors")
