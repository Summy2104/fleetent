"""add headers column to agent_mcp_servers

Custom HTTP headers (JSON object) sent verbatim on every request to an HTTP/WebSocket
MCP server — e.g. an ``X-API-Key`` the server requires that does not fit the
``Authorization: Bearer`` model. Stored as a JSON string; NULL/absent means no extra
headers. Sensitive values are masked when surfaced through the admin API.

Revision ID: 044
Revises: 043
Create Date: 2026-06-04

Owner module: connector-management
"""

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_mcp_servers", sa.Column("headers", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_mcp_servers", "headers")
