"""drop quota tables (descope non-functional quota half-feature)

Revision ID: 065
Revises: 064
Create Date: 2026-06-09

governance/quota.py created these tables at runtime via _init_db (never via alembic).
check_quota/record_usage had zero callers in production paths — quota was never enforced.
Descoped for v1; tables dropped here so deployed instances are cleaned up.
downgrade recreates them per the original _init_db DDL to preserve reversibility.
"""

import sqlalchemy as sa
from alembic import op

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quota_usage")
    op.execute("DROP TABLE IF EXISTS quotas")


def downgrade() -> None:
    op.create_table(
        "quotas",
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("token_limit", sa.Integer(), nullable=True),
        sa.Column("call_limit", sa.Integer(), nullable=True),
    )
    op.create_table(
        "quota_usage",
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
    )
