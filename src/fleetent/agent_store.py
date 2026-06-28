"""Agent definitions, bindings, and per-agent capability switches.

Schema lifecycle is owned by Alembic (single source of truth). The agents table
holds the current runtime config and per-agent capabilities in one place; MCP
bindings remain normalized in ``agent_mcp_servers``.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteConnection, SQLiteDatabase, create_database

_logger = logging.getLogger(__name__)
_UNSET: Any = object()

# Optional hook called with the agent's integer id just before the agent row is
# deleted. Platform may register this at startup for management-plane cleanup;
# standalone agents leave it None. Best-effort: exceptions
# are caught, logged, and suppressed so delete_agent always completes.
_delete_agent_hook: Callable[[int], None] | None = None


def set_delete_agent_hook(cb: Callable[[int], None]) -> None:
    """Register a pre-delete cleanup callback (called with the agent's integer id).

    Called once by the platform server lifespan. Must not be called by agent runtime code.
    """
    global _delete_agent_hook
    _delete_agent_hook = cb


_AGENT_ROW_COLUMNS = (
    "id, name, version, system_prompt, allowed_tools, features, plugins, allowed_skills, "
    "tenant_id, team_id, skills_dir, model_overrides, memory_namespace, icon, "
    "config_overrides, supports_dm, supports_groups"
)


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]
    version: int = 1
    # Extensible per-agent capability switches (SB3). Currently carries
    # `code_execution: bool | None`; SB5 reuses the same JSON column for
    # `sandbox_env`. Stored as a JSON TEXT column on the agents row.
    features: dict[str, Any] = field(default_factory=dict)
    # AR7 plugin allowlist: names of enabled plugins this agent may use. Expanded
    # to `{name}__*` namespace patterns and merged into the effective
    # `allowed_tools` so the agent_loop schema filter exposes only authorised
    # plugin tools.
    plugins: list[str] = field(default_factory=list)
    # agent-skill-scoping: per-agent skill catalog narrowing. Names of skills this
    # agent may SEE in the <available_skills> catalog. EMPTY = no narrowing (every
    # enabled skill stays visible) — the OPPOSITE default from `plugins`, because
    # skills are visible to all agents by default whereas plugin tools are not.
    # This is catalog visibility, NOT an authorization boundary.
    allowed_skills: list[str] = field(default_factory=list)
    tenant_id: str = "default"
    team_id: str | None = None
    skills_dir: str | None = None
    mcp_server_ids: list[str] | None = None
    model_overrides: dict[str, Any] = field(default_factory=dict)
    memory_namespace: str = "default"
    # Optional avatar emoji shown in the console; agent-level identity, not versioned.
    icon: str | None = None
    # Per-agent agent.yaml field overrides (governance/deployment/intelligence/access…),
    # deep-merged onto the materialized defaults. Agent-level, not versioned.
    config_overrides: dict[str, Any] = field(default_factory=dict)
    # Agent IM access capability switches are authored on the management-plane agent row.
    supports_dm: bool = False
    supports_groups: bool = False


def _db() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_caps(row: dict[str, Any]) -> dict[str, Any]:
    """Decode the per-agent capability columns, guarding legacy NULL rows."""
    return {
        # `or "{}"` guards a legacy row whose features value is NULL.
        "features": json.loads(row["features"] or "{}"),
        # `or "[]"` guards a legacy row predating the plugins column (NULL).
        "plugins": json.loads(row["plugins"] or "[]"),
        # `or "[]"` guards a legacy row predating allowed_skills (NULL); [] means
        # no narrowing (backward compatible).
        "allowed_skills": json.loads(row["allowed_skills"] or "[]"),
        # icon column added in migration 047; guard legacy rows that predate it.
        # `row` is a sqlite3.Row (no .get), so `in` membership is the guard, not row.get.
        "icon": (row["icon"] if "icon" in row else None),  # noqa: SIM401
        # config_overrides added in migration 053; guard legacy rows (NULL/absent -> {}).
        "config_overrides": (
            json.loads(row["config_overrides"] or "{}") if "config_overrides" in row else {}
        ),
        "supports_dm": bool(row["supports_dm"]) if "supports_dm" in row else False,
        "supports_groups": bool(row["supports_groups"]) if "supports_groups" in row else False,
    }


def _table_columns(conn: SQLiteConnection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _validate_team_tenant(
    conn: SQLiteConnection,
    *,
    agent_name: str,
    tenant_id: str,
    team_id: str | None,
) -> None:
    if team_id is None:
        return
    row = conn.execute(
        "SELECT tenant_id FROM teams WHERE id = :team_id", {"team_id": team_id}
    ).fetchone()
    if row is None:
        return
    team_tenant_id = str(row["tenant_id"])
    if team_tenant_id != tenant_id:
        raise ValueError(
            f"agent {agent_name!r} team {team_id!r} belongs to tenant {team_tenant_id!r}, "
            f"not agent tenant {tenant_id!r}"
        )


def create_agent(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    features: dict[str, Any] | None = None,
    plugins: list[str] | None = None,
    allowed_skills: list[str] | None = None,
    *,
    skills_dir: str | None = None,
    mcp_server_ids: list[str] | None = None,
    model_overrides: dict[str, Any] | None = None,
    memory_namespace: str = "default",
    tenant_id: str = "default",
    team_id: str | None = None,
    icon: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> Agent:
    """Create an agent in the current-state store."""
    features = features or {}
    plugins = plugins or []
    allowed_skills = allowed_skills or []
    config_overrides = config_overrides or {}
    db = _db()
    now = _now()
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM agents WHERE name = :name", {"name": name}).fetchone():
            raise ValueError(f"agent {name!r} already exists")
        _validate_team_tenant(conn, agent_name=name, tenant_id=tenant_id, team_id=team_id)
        agent_columns = _table_columns(conn, "agents")
        values: dict[str, Any] = {
            "name": name,
            "version": 1,
            "system_prompt": system_prompt,
            "allowed_tools": json.dumps(allowed_tools),
            "features": json.dumps(features),
            "plugins": json.dumps(plugins),
            "allowed_skills": json.dumps(allowed_skills),
            "created_at": now,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "skills_dir": skills_dir,
            "model_overrides": json.dumps(model_overrides or {}),
            "memory_namespace": memory_namespace,
            "icon": icon,
            "config_overrides": json.dumps(config_overrides),
        }
        insert_columns = [column for column in values if column in agent_columns]
        placeholders = ", ".join(f":{column}" for column in insert_columns)
        agent_id = conn.execute(
            f"INSERT INTO agents ({', '.join(insert_columns)}) VALUES ({placeholders})",
            {column: values[column] for column in insert_columns},
        ).lastrowid

        for server_id in sorted(set(mcp_server_ids or [])):
            conn.execute(
                "INSERT OR IGNORE INTO agent_mcp_servers "
                "(agent_id, server_id, created_at, created_by) "
                "VALUES (:agent_id, :server_id, :created_at, :created_by)",
                {
                    "agent_id": int(agent_id or 0),
                    "server_id": server_id,
                    "created_at": now,
                    "created_by": None,
                },
            )
    return Agent(
        id=int(agent_id or 0),
        name=name,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        version=1,
        features=features,
        plugins=plugins,
        allowed_skills=allowed_skills,
        tenant_id=tenant_id,
        team_id=team_id,
        skills_dir=skills_dir,
        mcp_server_ids=mcp_server_ids,
        model_overrides=model_overrides or {},
        memory_namespace=memory_namespace,
        icon=icon,
        config_overrides=config_overrides,
        supports_dm=False,
        supports_groups=False,
    )


def set_icon(name: str, icon: str | None) -> None:
    """Set an agent's avatar emoji (agent-level identity, not a new version)."""
    _db().execute("UPDATE agents SET icon = :icon WHERE name = :name", {"icon": icon, "name": name})


def set_identity(name: str, tenant_id: str, team_id: str | None) -> None:
    """Update an agent's tenant/team (agent-level identity, not a versioned change)."""
    update_agent_tenancy(name, tenant_id=tenant_id, team_id=team_id)


def update_agent_tenancy(name: str, tenant_id: str, team_id: str | None) -> None:
    """Update an agent's tenant/team after validating team ownership consistency."""
    db = _db()
    with db.transaction() as conn:
        _validate_team_tenant(conn, agent_name=name, tenant_id=tenant_id, team_id=team_id)
        conn.execute(
            "UPDATE agents SET tenant_id = :tenant_id, team_id = :team_id WHERE name = :name",
            {"tenant_id": tenant_id, "team_id": team_id, "name": name},
        )


def set_config_overrides(name: str, config_overrides: dict[str, Any]) -> None:
    """Replace an agent's agent.yaml field overrides (agent-level, not versioned)."""
    update_agent_config(name, config_overrides=config_overrides)


def set_im_capabilities(name: str, *, supports_dm: bool, supports_groups: bool) -> None:
    """Replace an agent's IM chat-type capability switches."""
    _db().execute(
        "UPDATE agents SET supports_dm = :supports_dm, supports_groups = :supports_groups "
        "WHERE name = :name",
        {
            "supports_dm": int(supports_dm),
            "supports_groups": int(supports_groups),
            "name": name,
        },
    )


def icons_by_name() -> dict[str, str]:
    """Map of agent name -> icon for the rows that have one (drives the list view)."""
    rows = _db().execute("SELECT name, icon FROM agents WHERE icon IS NOT NULL").fetchall()
    return {str(r["name"]): str(r["icon"]) for r in rows}


def _row_to_agent(row: dict[str, Any], *, mcp_server_ids: list[str] | None = None) -> Agent:
    return Agent(
        id=int(row["id"]),
        name=str(row["name"]),
        version=int(row["version"]) if row["version"] is not None else 1,
        system_prompt=str(row["system_prompt"]),
        allowed_tools=json.loads(row["allowed_tools"]),
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] is not None else "default",
        team_id=str(row["team_id"]) if row["team_id"] is not None else None,
        skills_dir=row["skills_dir"],
        mcp_server_ids=mcp_server_ids,
        model_overrides=json.loads(row["model_overrides"]) if row["model_overrides"] else {},
        memory_namespace=str(row["memory_namespace"]),
        **_parse_caps(row),
    )


def _get_agent_row(db: SQLiteDatabase, name: str) -> dict[str, Any] | None:
    return db.execute(
        f"SELECT {_AGENT_ROW_COLUMNS} FROM agents WHERE name = :name",
        {"name": name},
    ).fetchone()


def get_by_name(name: str) -> Agent | None:
    """Return the agent from the current-state row."""
    db = _db()
    row = _get_agent_row(db, name)
    if row is None:
        return None
    return _row_to_agent(row, mcp_server_ids=list_mcp_servers_for_agent(int(row["id"])))


def get_by_id(agent_id: int) -> Agent | None:
    """Return the agent by integer id from the current-state row."""
    db = _db()
    row = db.execute(
        f"SELECT {_AGENT_ROW_COLUMNS} FROM agents WHERE id = :agent_id",
        {"agent_id": agent_id},
    ).fetchone()
    if row is None:
        return None
    return _row_to_agent(row, mcp_server_ids=list_mcp_servers_for_agent(int(row["id"])))


def update_agent_config(
    name: str,
    *,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    skills_dir: str | None = None,
    mcp_server_ids: list[str] | None = None,
    model_overrides: dict[str, Any] | None = None,
    memory_namespace: str | None = None,
    features: dict[str, Any] | None = None,
    plugins: list[str] | None = None,
    allowed_skills: list[str] | None = None,
    tenant_id: str | None = None,
    team_id: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> Agent:
    """Update the current-state agent config in place and bump its version."""
    db = _db()
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT id, version, tenant_id, team_id
            FROM agents
            WHERE name = :name
            """,
            {"name": name},
        ).fetchone()
        if row is None:
            raise ValueError(f"agent {name!r} not found")

        next_tenant_id = tenant_id if tenant_id is not None else str(row["tenant_id"])
        next_team_id = team_id if team_id is not None else row["team_id"]
        _validate_team_tenant(
            conn,
            agent_name=name,
            tenant_id=next_tenant_id,
            team_id=None if next_team_id is None else str(next_team_id),
        )

        updates: dict[str, Any] = {"version": int(row["version"]) + 1}
        if system_prompt is not None:
            updates["system_prompt"] = system_prompt
        if allowed_tools is not None:
            updates["allowed_tools"] = json.dumps(allowed_tools)
        if skills_dir is not None:
            updates["skills_dir"] = skills_dir
        if model_overrides is not None:
            updates["model_overrides"] = json.dumps(model_overrides)
        if memory_namespace is not None:
            updates["memory_namespace"] = memory_namespace
        if features is not None:
            updates["features"] = json.dumps(features)
        if plugins is not None:
            updates["plugins"] = json.dumps(plugins)
        if allowed_skills is not None:
            updates["allowed_skills"] = json.dumps(allowed_skills)
        if tenant_id is not None:
            updates["tenant_id"] = tenant_id
        if team_id is not None:
            updates["team_id"] = team_id
        if config_overrides is not None:
            updates["config_overrides"] = json.dumps(config_overrides or {})

        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        conn.execute(
            f"UPDATE agents SET {assignments} WHERE name = :name",
            {"name": name, **updates},
        )

        if mcp_server_ids is not None:
            agent_id = int(row["id"])
            conn.execute(
                "DELETE FROM agent_mcp_servers WHERE agent_id = :agent_id",
                {"agent_id": agent_id},
            )
            for server_id in sorted(set(mcp_server_ids)):
                conn.execute(
                    "INSERT OR IGNORE INTO agent_mcp_servers "
                    "(agent_id, server_id, created_at, created_by) "
                    "VALUES (:agent_id, :server_id, :created_at, :created_by)",
                    {
                        "agent_id": agent_id,
                        "server_id": server_id,
                        "created_at": _now(),
                        "created_by": None,
                    },
                )

    agent = get_by_name(name)
    assert agent is not None
    return agent


def delete_agent(name: str) -> bool:
    """Hard-delete an agent and all its dependent rows in one transaction.

    Returns True when an agent was removed, False when no such agent exists.
    Every agent-referencing table carries FK→agents.id ON DELETE CASCADE
    (identity-model 阶段 2–4), so deleting the ``agents`` row cascades to
    bindings / satellites with no orphans — no manual child deletes needed.
    """
    db = _db()
    with db.transaction() as conn:
        agent = conn.execute("SELECT id FROM agents WHERE name = :name", {"name": name}).fetchone()
        if agent is None:
            return False
        agent_id = int(agent["id"])
        if _delete_agent_hook is not None:
            try:
                _delete_agent_hook(agent_id)
            except Exception:
                _logger.warning("delete_agent cleanup hook failed for agent_id=%s", agent_id)
        conn.execute("DELETE FROM agents WHERE id = :aid", {"aid": agent_id})
    return True


def get_agent_name_by_id(agent_id: int) -> str | None:
    row = _db().execute("SELECT name FROM agents WHERE id = :aid", {"aid": agent_id}).fetchone()
    return None if row is None else str(row["name"])


def list_all_names() -> list[str]:
    """Every authored agent's name, sorted (drives platform-wide re-materialize)."""
    rows = _db().execute("SELECT name FROM agents ORDER BY name").fetchall()
    return [str(r["name"]) for r in rows]


def assign_user(user_id: str, agent_id: int) -> None:
    _db().execute(
        "INSERT OR IGNORE INTO user_agents (user_id, agent_id) VALUES (:user_id, :agent_id)",
        {"user_id": user_id, "agent_id": agent_id},
    )


def unassign_user(user_id: str, agent_id: int) -> None:
    _db().execute(
        "DELETE FROM user_agents WHERE user_id = :user_id AND agent_id = :agent_id",
        {"user_id": user_id, "agent_id": agent_id},
    )


def list_users_for_agent(agent_id: int) -> list[str]:
    rows = (
        _db()
        .execute(
            "SELECT user_id FROM user_agents WHERE agent_id = :agent_id ORDER BY user_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [str(row["user_id"]) for row in rows]


def list_im_groups_for_agent(agent_id: int) -> list[dict[str, str]]:
    rows = (
        _db()
        .execute(
            """
            SELECT platform, group_id
            FROM agent_im_groups
            WHERE agent_id = :agent_id
            ORDER BY platform, group_id
            """,
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [{"platform": str(row["platform"]), "group_id": str(row["group_id"])} for row in rows]


def bind_mcp_server(agent_id: int, server_id: str, created_by: str | None = None) -> None:
    _db().execute(
        "INSERT OR IGNORE INTO agent_mcp_servers "
        "(agent_id, server_id, created_at, created_by) "
        "VALUES (:agent_id, :server_id, :created_at, :created_by)",
        {
            "agent_id": agent_id,
            "server_id": server_id,
            "created_at": _now(),
            "created_by": created_by,
        },
    )


def unbind_mcp_server(agent_id: int, server_id: str) -> None:
    _db().execute(
        "DELETE FROM agent_mcp_servers WHERE agent_id = :agent_id AND server_id = :server_id",
        {"agent_id": agent_id, "server_id": server_id},
    )


def list_mcp_servers_for_agent(agent_id: int) -> list[str]:
    rows = (
        _db()
        .execute(
            "SELECT server_id FROM agent_mcp_servers WHERE agent_id = :agent_id ORDER BY server_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [str(row["server_id"]) for row in rows]


def _get_default_agent_name() -> str | None:
    # The default agent is the file index's `bindings.default` winner (zero-DB),
    # not a global Settings field (dissolved in config consolidation).
    from fleetent import agent_config

    return agent_config.current().default


def get_default_agent() -> Agent | None:
    name = _get_default_agent_name()
    if not name:
        return None
    return get_by_name(name)
