"""add connectors config table

Revision ID: 013
Revises: 012
Create Date: 2026-06-02

Owner module: platform / connector-management

Only the OAuth connector *config catalog* is owned here. Per-user credentials,
OAuth consent/refresh, and revoke semantics belong to the connectors engine domain;
MCP connection state belongs to the mcp domain. client_secret is never stored in
this table (it stays in env / secret injection).
"""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False, server_default="oauth2"),
        # oauth_config JSON: authorize/token endpoints, scopes, client_id (NO secret).
        sa.Column("oauth_config", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("connectors")
