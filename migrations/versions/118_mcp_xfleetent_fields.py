"""mcp x-fleetent fields: degrade_mode / file_root / file_isolation / approval_rules

Revision ID: 118
Revises: 117
Create Date: 2026-07-03

Owner module: connector-management
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    op.add_column(
        "mcp_servers",
        sa.Column("degrade_mode", sa.Text(), nullable=False, server_default="degrade"),
    )
    op.add_column(
        "mcp_servers", sa.Column("file_root", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "mcp_servers",
        sa.Column("file_isolation", sa.Text(), nullable=False, server_default="on"),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("approval_rules", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("approval_rules")
        batch_op.drop_column("file_isolation")
        batch_op.drop_column("file_root")
        batch_op.drop_column("degrade_mode")
