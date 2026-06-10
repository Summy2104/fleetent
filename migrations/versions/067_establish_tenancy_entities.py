"""Establish tenancy entities: tenants, teams, default principal.

Creates tenants and teams root tables (uuid string PKs) and inserts the
default principal row (id='default').  Subsequent migrations 068/069 will
bring users into Alembic and upgrade existing FK columns.

Revision ID: 067
Revises: 066
Create Date: 2026-06-10
"""

import datetime

import sqlalchemy as sa
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

_DEFAULT_TENANT_ID = "default"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        # approver_user_id FK→users added in migration 069 (after users enters Alembic)
        sa.Column("approver_user_id", sa.Text(), nullable=True),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Text(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        # approver_user_id FK→users added in migration 069
        sa.Column("approver_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    now = datetime.datetime.now(datetime.UTC).isoformat()
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO tenants (id, name, status, created_at) "
            "VALUES (:id, :name, :status, :created_at)"
        ).bindparams(id=_DEFAULT_TENANT_ID, name="Default", status="active", created_at=now)
    )


def downgrade() -> None:
    op.drop_table("teams")
    op.drop_table("tenants")
