"""Descope model_routes and normalize tenancy FK delete semantics.

Revision ID: 086
Revises: 085
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _select_expr(columns: set[str], name: str, default_sql: str) -> str:
    return name if name in columns else default_sql


def _drop_model_routes() -> None:
    if not _has_table("model_routes"):
        return
    op.drop_index("idx_model_routes_task", table_name="model_routes")
    op.drop_table("model_routes")


def _create_model_routes() -> None:
    if _has_table("model_routes"):
        return
    op.create_table(
        "model_routes",
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("task_type", "provider_id"),
    )
    op.create_index("idx_model_routes_task", "model_routes", ["task_type", "priority"])


def _rebuild_users(*, ondelete: str) -> None:
    if not _has_table("users"):
        return
    bind = op.get_bind()
    columns = _column_names("users")
    bind.exec_driver_sql(
        f"""
        CREATE TABLE users__new (
            id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            email TEXT,
            password_hash TEXT,
            role TEXT DEFAULT 'viewer' NOT NULL,
            status TEXT DEFAULT 'active' NOT NULL,
            must_reset INTEGER DEFAULT '0' NOT NULL,
            tenant_id TEXT DEFAULT 'default' NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE {ondelete}
        )
        """
    )
    bind.exec_driver_sql(
        f"""
        INSERT INTO users__new
            (id, name, created_at, email, password_hash, role, status, must_reset, tenant_id)
        SELECT
            id,
            name,
            created_at,
            {_select_expr(columns, "email", "NULL")},
            {_select_expr(columns, "password_hash", "NULL")},
            {_select_expr(columns, "role", "'viewer'")},
            {_select_expr(columns, "status", "'active'")},
            {_select_expr(columns, "must_reset", "0")},
            {_select_expr(columns, "tenant_id", "'default'")}
        FROM users
        """
    )
    op.drop_table("users")
    op.rename_table("users__new", "users")


def _rebuild_agents(*, tenant_ondelete: str, team_ondelete: str) -> None:
    if not _has_table("agents"):
        return
    bind = op.get_bind()
    columns = _column_names("agents")
    bind.exec_driver_sql(
        f"""
        CREATE TABLE agents__new (
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
            config_overrides TEXT DEFAULT '{{}}' NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_agents_tenant_id
                FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE {tenant_ondelete},
            CONSTRAINT fk_agents_team_id
                FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE {team_ondelete},
            UNIQUE (name)
        )
        """
    )
    bind.exec_driver_sql(
        f"""
        INSERT INTO agents__new
            (id, name, system_prompt, allowed_tools, created_at, tenant_id, team_id,
             active_version_id, features, plugins, allowed_skills, icon, config_overrides)
        SELECT
            id,
            name,
            system_prompt,
            allowed_tools,
            created_at,
            {_select_expr(columns, "tenant_id", "'default'")},
            {_select_expr(columns, "team_id", "NULL")},
            {_select_expr(columns, "active_version_id", "NULL")},
            {_select_expr(columns, "features", "NULL")},
            {_select_expr(columns, "plugins", "'[]'")},
            {_select_expr(columns, "allowed_skills", "'[]'")},
            {_select_expr(columns, "icon", "NULL")},
            {_select_expr(columns, "config_overrides", "'{}'")}
        FROM agents
        """
    )
    op.drop_table("agents")
    op.rename_table("agents__new", "agents")


def _rebuild_tenants(*, ondelete: str) -> None:
    if not _has_table("tenants"):
        return
    bind = op.get_bind()
    columns = _column_names("tenants")
    bind.exec_driver_sql(
        f"""
        CREATE TABLE tenants__new (
            id TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active' NOT NULL,
            created_at TEXT NOT NULL,
            approver_user_id TEXT,
            PRIMARY KEY (id),
            CONSTRAINT fk_tenants_approver_user_id
                FOREIGN KEY(approver_user_id) REFERENCES users (id) ON DELETE {ondelete}
        )
        """
    )
    bind.exec_driver_sql(
        f"""
        INSERT INTO tenants__new (id, name, status, created_at, approver_user_id)
        SELECT
            id,
            name,
            {_select_expr(columns, "status", "'active'")},
            created_at,
            {_select_expr(columns, "approver_user_id", "NULL")}
        FROM tenants
        """
    )
    op.drop_table("tenants")
    op.rename_table("tenants__new", "tenants")


def _rebuild_teams(*, tenant_ondelete: str, approver_ondelete: str) -> None:
    if not _has_table("teams"):
        return
    bind = op.get_bind()
    columns = _column_names("teams")
    bind.exec_driver_sql(
        f"""
        CREATE TABLE teams__new (
            id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            approver_user_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_teams_approver_user_id
                FOREIGN KEY(approver_user_id) REFERENCES users (id) ON DELETE {approver_ondelete},
            FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE {tenant_ondelete}
        )
        """
    )
    bind.exec_driver_sql(
        f"""
        INSERT INTO teams__new (id, tenant_id, name, approver_user_id, created_at)
        SELECT
            id,
            {_select_expr(columns, "tenant_id", "'default'")},
            name,
            {_select_expr(columns, "approver_user_id", "NULL")},
            created_at
        FROM teams
        """
    )
    op.drop_table("teams")
    op.rename_table("teams__new", "teams")


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        _drop_model_routes()
        _rebuild_users(ondelete="RESTRICT")
        _rebuild_tenants(ondelete="SET NULL")
        _rebuild_teams(tenant_ondelete="RESTRICT", approver_ondelete="SET NULL")
        _rebuild_agents(tenant_ondelete="RESTRICT", team_ondelete="RESTRICT")
    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        _rebuild_agents(tenant_ondelete="NO ACTION", team_ondelete="NO ACTION")
        _rebuild_teams(tenant_ondelete="NO ACTION", approver_ondelete="NO ACTION")
        _rebuild_tenants(ondelete="NO ACTION")
        _rebuild_users(ondelete="NO ACTION")
        _create_model_routes()
    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")
