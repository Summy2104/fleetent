"""Upgrade existing tenant_id/team_id columns to FK constraints.

Now that tenants/teams and users (with tenant_id) are established, this
migration upgrades bare TEXT columns to proper FK references:

  agents.tenant_id      → tenants(id)
  agents.team_id        → teams(id)   [nullable, no change to nullability]
  traces.tenant_id      → tenants(id)
  knowledge_bases.tenant_id → tenants(id)
  long_term_context_policies.tenant_id → tenants(id)

Also adds FK from approver_user_id columns to users, completing the two-level
approver chain:
  tenants.approver_user_id → users(id)
  teams.approver_user_id   → users(id)

All existing values remain unchanged; only the FK metadata is added.

Revision ID: 069
Revises: 068
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(name)


def _has_foreign_key(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def _rebuild_teams_without_approver_fk() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE teams__old (
            id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            approver_user_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO teams__old (id, tenant_id, name, approver_user_id, created_at)
        SELECT id, tenant_id, name, approver_user_id, created_at FROM teams
        """
    )
    op.drop_table("teams")
    op.rename_table("teams__old", "teams")


def _rebuild_tenants_without_approver_fk() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE tenants__old (
            id TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active' NOT NULL,
            created_at TEXT NOT NULL,
            approver_user_id TEXT,
            PRIMARY KEY (id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO tenants__old (id, name, status, created_at, approver_user_id)
        SELECT id, name, status, created_at, approver_user_id FROM tenants
        """
    )
    op.drop_table("tenants")
    op.rename_table("tenants__old", "tenants")


def _rebuild_agents_without_tenancy_fks() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agents__old (
            id INTEGER NOT NULL,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            allowed_tools TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            tenant_id TEXT DEFAULT 'default' NOT NULL,
            team_id TEXT,
            active_version_id INTEGER,
            features TEXT,
            plugins TEXT DEFAULT '[]' NOT NULL,
            allowed_skills TEXT DEFAULT '[]' NOT NULL,
            icon TEXT,
            config_overrides TEXT DEFAULT '{}' NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (name)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agents__old
            (id, name, system_prompt, allowed_tools, created_at, tenant_id, team_id,
             active_version_id, features, plugins, allowed_skills, icon, config_overrides)
        SELECT
            id, name, system_prompt, allowed_tools, created_at, tenant_id, team_id,
            active_version_id, features, plugins, allowed_skills, icon, config_overrides
        FROM agents
        """
    )
    op.drop_table("agents")
    op.rename_table("agents__old", "agents")


def upgrade() -> None:
    # agents: tenant_id FK→tenants, team_id FK→teams
    with op.batch_alter_table("agents", recreate="always") as batch:
        batch.create_foreign_key("fk_agents_tenant_id", "tenants", ["tenant_id"], ["id"])
        batch.create_foreign_key("fk_agents_team_id", "teams", ["team_id"], ["id"])

    # traces: tenant_id FK→tenants
    with op.batch_alter_table("traces", recreate="always") as batch:
        batch.create_foreign_key("fk_traces_tenant_id", "tenants", ["tenant_id"], ["id"])

    # knowledge_bases: tenant_id FK→tenants
    # knowledge_bases has a composite PK (tenant_id, kb_id) and child tables reference it;
    # batch mode handles this correctly on SQLite.
    with op.batch_alter_table("knowledge_bases", recreate="always") as batch:
        batch.create_foreign_key("fk_knowledge_bases_tenant_id", "tenants", ["tenant_id"], ["id"])

    # long_term_context_policies: tenant_id FK→tenants
    with op.batch_alter_table("long_term_context_policies", recreate="always") as batch:
        batch.create_foreign_key("fk_ltc_policies_tenant_id", "tenants", ["tenant_id"], ["id"])

    # tenants.approver_user_id FK→users (now that users is in Alembic)
    with op.batch_alter_table("tenants", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_tenants_approver_user_id", "users", ["approver_user_id"], ["id"]
        )

    # teams.approver_user_id FK→users
    with op.batch_alter_table("teams", recreate="always") as batch:
        batch.create_foreign_key("fk_teams_approver_user_id", "users", ["approver_user_id"], ["id"])


def downgrade() -> None:
    _rebuild_teams_without_approver_fk()

    _rebuild_tenants_without_approver_fk()

    with op.batch_alter_table("long_term_context_policies", recreate="always") as batch:
        batch.drop_constraint("fk_ltc_policies_tenant_id", type_="foreignkey")

    with op.batch_alter_table("knowledge_bases", recreate="always") as batch:
        batch.drop_constraint("fk_knowledge_bases_tenant_id", type_="foreignkey")

    if _has_table("traces") and _has_foreign_key("traces", "fk_traces_tenant_id"):
        with op.batch_alter_table("traces", recreate="always") as batch:
            batch.drop_constraint("fk_traces_tenant_id", type_="foreignkey")

    _rebuild_agents_without_tenancy_fks()
