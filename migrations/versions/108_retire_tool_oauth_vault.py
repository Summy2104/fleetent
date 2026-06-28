"""retire tool oauth vault

Revision ID: 108
Revises: 107
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    for table in ("agent_service_grants", "external_credentials", "external_services"):
        if _has_table(table):
            op.drop_table(table)


def downgrade() -> None:
    # Forward-only retirement: the dropped vault tables carried no production traffic and are
    # intentionally not recreated on downgrade.
    pass
