"""Agent definitions, user/channel bindings, ownership, and per-agent capability
switches on the unified db runtime.

Schema lives entirely in alembic migrations (single source of truth): the agents
table is created on the trunk and gains tenant_id/team_id (030) plus the
capability columns features/plugins/allowed_skills (032-034). No inline _init_db.
"""

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_AGENT_COLUMNS = (
    "id, name, system_prompt, allowed_tools, features, plugins, allowed_skills, tenant_id, team_id"
)


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]
    # Extensible per-agent capability switches (SB3). Currently carries
    # `code_execution: bool | None`; SB5 reuses the same JSON column for
    # `sandbox_env`. Stored as a JSON TEXT column, mirroring `allowed_tools`.
    features: dict[str, Any] = field(default_factory=dict)
    # AR7 plugin allowlist: names of enabled plugins this agent may use. Expanded
    # to `{name}__*` namespace patterns and merged into the effective
    # `allowed_tools` so the agent_loop schema filter exposes only authorised
    # plugin tools. Stored as a JSON TEXT column, mirroring `allowed_tools`.
    plugins: list[str] = field(default_factory=list)
    # agent-skill-scoping: per-agent skill catalog narrowing. Names of skills this
    # agent may SEE in the <available_skills> catalog. EMPTY = no narrowing (every
    # enabled skill stays visible) — the OPPOSITE default from `plugins`, because
    # skills are visible to all agents by default whereas plugin tools are not.
    # This is catalog visibility, NOT an authorization boundary.
    allowed_skills: list[str] = field(default_factory=list)
    tenant_id: str = "default"
    team_id: str | None = None


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _join_cols(alias: str) -> str:
    """Qualify `_AGENT_COLUMNS` with a table alias for JOIN queries."""
    return ", ".join(f"{alias}.{c.strip()}" for c in _AGENT_COLUMNS.split(","))


def _row_to_agent(row: dict[str, Any]) -> Agent:
    return Agent(
        id=int(row["id"]),
        name=str(row["name"]),
        system_prompt=str(row["system_prompt"]),
        allowed_tools=json.loads(row["allowed_tools"]),
        # `or "{}"` guards a legacy row whose features value is NULL.
        features=json.loads(row["features"] or "{}"),
        # `or "[]"` guards a legacy row predating the plugins column (NULL).
        plugins=json.loads(row["plugins"] or "[]"),
        # `or "[]"` guards a legacy row predating allowed_skills (NULL); [] means
        # no narrowing (backward compatible).
        allowed_skills=json.loads(row["allowed_skills"] or "[]"),
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] is not None else "default",
        team_id=str(row["team_id"]) if row["team_id"] is not None else None,
    )


def create_agent(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    features: dict[str, Any] | None = None,
    plugins: list[str] | None = None,
    allowed_skills: list[str] | None = None,
    *,
    tenant_id: str = "default",
    team_id: str | None = None,
) -> Agent:
    features = features or {}
    plugins = plugins or []
    allowed_skills = allowed_skills or []
    result = _database().execute(
        "INSERT INTO agents"
        " (name, system_prompt, allowed_tools, features, plugins, allowed_skills,"
        " created_at, tenant_id, team_id)"
        " VALUES (:name, :system_prompt, :allowed_tools, :features, :plugins,"
        " :allowed_skills, :created_at, :tenant_id, :team_id)",
        {
            "name": name,
            "system_prompt": system_prompt,
            "allowed_tools": json.dumps(allowed_tools),
            "features": json.dumps(features),
            "plugins": json.dumps(plugins),
            "allowed_skills": json.dumps(allowed_skills),
            "created_at": _now(),
            "tenant_id": tenant_id,
            "team_id": team_id,
        },
    )
    agent_id = result.lastrowid
    assert agent_id is not None
    return Agent(
        id=agent_id,
        name=name,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        features=features,
        plugins=plugins,
        allowed_skills=allowed_skills,
        tenant_id=tenant_id,
        team_id=team_id,
    )


def get_by_name(name: str) -> Agent | None:
    row = (
        _database()
        .execute(
            f"SELECT {_AGENT_COLUMNS} FROM agents WHERE name = :name",
            {"name": name},
        )
        .fetchone()
    )
    return _row_to_agent(row) if row else None


def assign_user(user_id: str, agent_id: int) -> None:
    _database().execute(
        "INSERT OR IGNORE INTO user_agents (user_id, agent_id) VALUES (:user_id, :agent_id)",
        {"user_id": user_id, "agent_id": agent_id},
    )


def get_agent_for_user(user_id: str) -> Agent | None:
    row = (
        _database()
        .execute(
            f"""SELECT {_join_cols("a")}
               FROM agents a
               JOIN user_agents ua ON ua.agent_id = a.id
               WHERE ua.user_id = :user_id
               LIMIT 1""",
            {"user_id": user_id},
        )
        .fetchone()
    )
    return _row_to_agent(row) if row else None


def assign_channel(platform: str, channel_id: str, agent_id: int) -> None:
    _database().execute(
        "INSERT OR REPLACE INTO channel_agents (platform, channel_id, agent_id, created_at)"
        " VALUES (:platform, :channel_id, :agent_id, :created_at)",
        {
            "platform": platform,
            "channel_id": channel_id,
            "agent_id": agent_id,
            "created_at": _now(),
        },
    )


def unassign_channel(platform: str, channel_id: str) -> None:
    _database().execute(
        "DELETE FROM channel_agents WHERE platform = :platform AND channel_id = :channel_id",
        {"platform": platform, "channel_id": channel_id},
    )


def get_agent_for_channel(platform: str, channel_id: str) -> Agent | None:
    row = (
        _database()
        .execute(
            f"""SELECT {_join_cols("a")}
               FROM agents a
               JOIN channel_agents ca ON ca.agent_id = a.id
               WHERE ca.platform = :platform AND ca.channel_id = :channel_id
               LIMIT 1""",
            {"platform": platform, "channel_id": channel_id},
        )
        .fetchone()
    )
    return _row_to_agent(row) if row else None


def _get_default_agent_name() -> str | None:
    return Settings(anthropic_api_key="").default_agent_name


def get_default_agent() -> Agent | None:
    name = _get_default_agent_name()
    if not name:
        return None
    return get_by_name(name)
