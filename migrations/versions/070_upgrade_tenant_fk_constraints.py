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
        batch.create_foreign_key(
            "fk_knowledge_bases_tenant_id", "tenants", ["tenant_id"], ["id"]
        )

    # long_term_context_policies: tenant_id FK→tenants
    with op.batch_alter_table("long_term_context_policies", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_ltc_policies_tenant_id", "tenants", ["tenant_id"], ["id"]
        )

    # tenants.approver_user_id FK→users (now that users is in Alembic)
    with op.batch_alter_table("tenants", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_tenants_approver_user_id", "users", ["approver_user_id"], ["id"]
        )

    # teams.approver_user_id FK→users
    with op.batch_alter_table("teams", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_teams_approver_user_id", "users", ["approver_user_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("teams", recreate="always") as batch:
        batch.drop_constraint("fk_teams_approver_user_id", type_="foreignkey")

    with op.batch_alter_table("tenants", recreate="always") as batch:
        batch.drop_constraint("fk_tenants_approver_user_id", type_="foreignkey")

    with op.batch_alter_table("long_term_context_policies", recreate="always") as batch:
        batch.drop_constraint("fk_ltc_policies_tenant_id", type_="foreignkey")

    with op.batch_alter_table("knowledge_bases", recreate="always") as batch:
        batch.drop_constraint("fk_knowledge_bases_tenant_id", type_="foreignkey")

    with op.batch_alter_table("traces", recreate="always") as batch:
        batch.drop_constraint("fk_traces_tenant_id", type_="foreignkey")

    with op.batch_alter_table("agents", recreate="always") as batch:
        batch.drop_constraint("fk_agents_team_id", type_="foreignkey")
        batch.drop_constraint("fk_agents_tenant_id", type_="foreignkey")
