"""Drop dormant long-term context policy table.

Revision ID: 081
Revises: 080
Create Date: 2026-06-13
"""

import sqlalchemy as sa
from alembic import op

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    if _has_table("long_term_context_policies"):
        op.drop_table("long_term_context_policies")


def downgrade() -> None:
    op.create_table(
        "long_term_context_policies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("user_memory_enabled", sa.Integer(), nullable=False),
        sa.Column("tenant_shared_memory_enabled", sa.Integer(), nullable=False),
        sa.Column("team_shared_memory_enabled", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_enabled", sa.Integer(), nullable=False),
        sa.Column("user_memory_max_tokens", sa.Integer(), nullable=False),
        sa.Column("user_memory_top_k", sa.Integer(), nullable=False),
        sa.Column("tenant_shared_memory_max_tokens", sa.Integer(), nullable=False),
        sa.Column("tenant_shared_memory_top_k", sa.Integer(), nullable=False),
        sa.Column("team_shared_memory_max_tokens", sa.Integer(), nullable=False),
        sa.Column("team_shared_memory_top_k", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_max_tokens", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_top_k", sa.Integer(), nullable=False),
        sa.Column("conflict_preference", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_ltc_policies_tenant_id"),
    )
    op.create_index(
        "idx_long_term_context_policies_scope",
        "long_term_context_policies",
        ["tenant_id", "agent_id"],
        unique=True,
    )
