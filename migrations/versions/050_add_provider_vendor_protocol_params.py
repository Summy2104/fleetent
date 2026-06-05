"""add model_providers vendor/protocol/api_key_env/params

Extend the provider config to mirror the runtime route shape: a vendor label
(``provider``), wire ``protocol`` (e.g. openai_chat), an env-reference for the key
(``api_key_env``, alongside the existing raw ``api_key``), and a free-form ``params``
JSON blob (temperature/top_p/…). All nullable; legacy rows default to NULL.

Revision ID: 050
Revises: 049
Create Date: 2026-06-05

Owner module: model-provider-management
"""

import sqlalchemy as sa
from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in ("provider", "protocol", "api_key_env", "params"):
        op.add_column("model_providers", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("model_providers") as batch_op:
        for col in ("params", "api_key_env", "protocol", "provider"):
            batch_op.drop_column(col)
