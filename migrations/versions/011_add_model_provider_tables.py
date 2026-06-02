"""add model provider admin tables

Revision ID: 011
Revises: 010
Create Date: 2026-06-02

Owner module: platform / model-provider-management
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("extra_params", sa.Text(), nullable=True),
        # Pricing is intentionally nullable: NULL means "未配置" (unset), which is
        # distinct from an explicit 0.0 (configured as free).
        sa.Column("input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("output_price_per_1k", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_routes",
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("task_type", "provider_id"),
    )
    op.create_index("idx_model_routes_task", "model_routes", ["task_type", "priority"])


def downgrade() -> None:
    op.drop_index("idx_model_routes_task", table_name="model_routes")
    op.drop_table("model_routes")
    op.drop_table("model_providers")
