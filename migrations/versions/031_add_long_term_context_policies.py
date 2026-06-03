"""Add long-term context policy table.

Wide tenant-default + agent-override rows controlling source enablement and
per-source budgets for User Memory, Shared Memory (tenant/team), and Knowledge
Base. One tenant-default row per tenant (agent_id NULL) and one row per
(tenant_id, agent_id) override.

Revision ID: 031
Revises: 030
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    )
    # One row per scope: tenant-default rows share the sentinel '' agent key so a
    # unique index enforces a single default per tenant and a single row per agent.
    op.create_index(
        "idx_long_term_context_policies_scope",
        "long_term_context_policies",
        ["tenant_id", "agent_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_long_term_context_policies_scope",
        table_name="long_term_context_policies",
    )
    op.drop_table("long_term_context_policies")
