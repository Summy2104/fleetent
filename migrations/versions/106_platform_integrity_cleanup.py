"""Platform integrity cleanup.

Revision ID: 106
Revises: 105
Create Date: 2026-06-28
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None

_logger = logging.getLogger("alembic.runtime.migration")


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _log(message: str) -> None:
    _logger.info(message)


def _delete_orphan_api_keys() -> None:
    bind = op.get_bind()
    orphan_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) AS count
            FROM api_keys
            WHERE user_id NOT IN (SELECT id FROM users)
            """
        )
    ).scalar_one()
    if orphan_count:
        _log(f"migration 106 deleting {orphan_count} orphan api_keys rows")
        bind.execute(
            sa.text(
                """
                DELETE FROM api_keys
                WHERE user_id NOT IN (SELECT id FROM users)
                """
            )
        )


def _fail_on_cross_tenant_team_refs() -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
            SELECT agents.id, agents.name, agents.tenant_id AS agent_tenant_id,
                   agents.team_id, teams.tenant_id AS team_tenant_id
            FROM agents
            JOIN teams ON teams.id = agents.team_id
            WHERE agents.team_id IS NOT NULL
              AND teams.tenant_id != agents.tenant_id
            ORDER BY agents.id
            """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    details = "; ".join(
        "agent_id={id} name={name} agent_tenant={agent_tenant_id} team_id={team_id} "
        "team_tenant={team_tenant_id}".format(**row)
        for row in rows
    )
    raise RuntimeError(f"cross-tenant agent.team_id references detected: {details}")


def _rebuild_teams(*, with_composite_unique: bool) -> None:
    if not _has_table("teams"):
        return
    with op.batch_alter_table("teams", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "fk_teams_tenant_id",
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_teams_approver_user_id",
            "users",
            ["approver_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        if with_composite_unique:
            batch_op.create_unique_constraint("uq_teams_id_tenant_id", ["id", "tenant_id"])


def _rebuild_agents(*, with_composite_team_fk: bool) -> None:
    if not _has_table("agents"):
        return
    with op.batch_alter_table("agents", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "fk_agents_tenant_id",
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        if with_composite_team_fk:
            batch_op.create_foreign_key(
                "fk_agents_team_tenant_id",
                "teams",
                ["team_id", "tenant_id"],
                ["id", "tenant_id"],
                ondelete="RESTRICT",
            )
        else:
            batch_op.create_foreign_key(
                "fk_agents_team_id",
                "teams",
                ["team_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def _rebuild_api_keys(*, with_user_fk: bool) -> None:
    if not _has_table("api_keys"):
        return
    with op.batch_alter_table("api_keys", recreate="always") as batch_op:
        if with_user_fk:
            batch_op.create_foreign_key(
                "fk_api_keys_user_id",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )


def upgrade() -> None:
    if not (_has_table("teams") and _has_table("agents") and _has_table("api_keys")):
        return
    _delete_orphan_api_keys()
    _fail_on_cross_tenant_team_refs()
    _rebuild_teams(with_composite_unique=True)
    _rebuild_agents(with_composite_team_fk=True)
    _rebuild_api_keys(with_user_fk=True)


def downgrade() -> None:
    if not (_has_table("teams") and _has_table("agents") and _has_table("api_keys")):
        return
    _rebuild_api_keys(with_user_fk=False)
    _rebuild_agents(with_composite_team_fk=False)
    _rebuild_teams(with_composite_unique=False)
