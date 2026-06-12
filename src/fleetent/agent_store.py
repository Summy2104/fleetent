"""Agent definitions, immutable version snapshots, user/channel bindings, and
per-agent capability switches.

Schema lifecycle is owned by Alembic (single source of truth): the agents table
is created on the trunk, gains tenant_id/team_id (030), active_version_id (033),
and the capability columns features/plugins/allowed_skills (036-038). This store
reads and writes through the shared DB runtime boundary using named parameters;
it never creates schema.

Two concerns live side by side, reconciled during the next<-main integration:

* **Versioning** (main): the runtime-facing fields (system_prompt, allowed_tools,
  skills_dir, mcp_server_ids, model_overrides, memory_namespace) live in
  ``agent_versions``; ``agents.active_version_id`` points at the active snapshot.
  This drives the admin console and the snapshot-based ``agent_runtime``.
* **Capabilities** (next): features/plugins/allowed_skills are per-agent (NOT
  per-version) switches stored as JSON TEXT columns on ``agents``. The flat
  ``Agent`` dataclass exposes them so the parameter-style agent_loop pipeline can
  read them directly. ``get_by_name`` returns runtime fields from the active
  version and caps from the agent row.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteConnection, SQLiteDatabase, create_database

_UNSET: Any = object()

# Agent-row columns beyond the version-derived runtime fields. Caps are not
# versioned, so they are read straight off the agents row.
_AGENT_ROW_COLUMNS = (
    "id, name, active_version_id, features, plugins, allowed_skills, tenant_id, team_id, "
    "icon, config_overrides"
)


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]
    active_version_id: int | None = None
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


@dataclass
class AgentVersion:
    id: int
    agent_id: int
    version: int
    system_prompt: str
    allowed_tools: list[str]
    skills_dir: str | None
    mcp_server_ids: list[str] | None
    model_overrides: dict[str, Any]
    memory_namespace: str
    created_at: str
    is_active: bool = False


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
    }


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
    """Create an agent plus its version-1 snapshot in a single transaction.

    Capabilities (features/plugins/allowed_skills) are stored on the agents row;
    runtime fields are snapshotted into agent_versions v1.
    """
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
        agent_id = conn.execute(
            "INSERT INTO agents "
            "(name, system_prompt, allowed_tools, features, plugins, allowed_skills, "
            " created_at, tenant_id, team_id, icon, config_overrides) "
            "VALUES (:name, :system_prompt, :allowed_tools, :features, :plugins, "
            " :allowed_skills, :created_at, :tenant_id, :team_id, :icon, :config_overrides)",
            {
                "name": name,
                "system_prompt": system_prompt,
                "allowed_tools": json.dumps(allowed_tools),
                "features": json.dumps(features),
                "plugins": json.dumps(plugins),
                "allowed_skills": json.dumps(allowed_skills),
                "created_at": now,
                "tenant_id": tenant_id,
                "team_id": team_id,
                "icon": icon,
                "config_overrides": json.dumps(config_overrides),
            },
        ).lastrowid
        version_id = _insert_version(
            conn,
            agent_id=int(agent_id or 0),
            version=1,
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            skills_dir=skills_dir,
            mcp_server_ids=mcp_server_ids,
            model_overrides=model_overrides or {},
            memory_namespace=memory_namespace,
            now=now,
        )
        conn.execute(
            "UPDATE agents SET active_version_id = :vid WHERE id = :aid",
            {"vid": version_id, "aid": agent_id},
        )
    return Agent(
        id=int(agent_id or 0),
        name=name,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        active_version_id=version_id,
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
    _db().execute(
        "UPDATE agents SET config_overrides = :co WHERE name = :name",
        {"co": json.dumps(config_overrides or {}), "name": name},
    )


def icons_by_name() -> dict[str, str]:
    """Map of agent name -> icon for the rows that have one (drives the list view)."""
    rows = _db().execute("SELECT name, icon FROM agents WHERE icon IS NOT NULL").fetchall()
    return {str(r["name"]): str(r["icon"]) for r in rows}


def _insert_version(
    conn: SQLiteConnection,
    *,
    agent_id: int,
    version: int,
    system_prompt: str,
    allowed_tools: list[str],
    skills_dir: str | None,
    mcp_server_ids: list[str] | None,
    model_overrides: dict[str, Any],
    memory_namespace: str,
    now: str,
    created_by_user_id: str | None = None,
) -> int:
    version_id = conn.execute(
        "INSERT INTO agent_versions "
        "(agent_id, version, system_prompt, allowed_tools, skills_dir, mcp_server_ids, "
        " model_overrides, memory_namespace, created_by_user_id, created_at) "
        "VALUES (:agent_id, :version, :system_prompt, :allowed_tools, :skills_dir, "
        " :mcp_server_ids, :model_overrides, :memory_namespace, :created_by, :created_at)",
        {
            "agent_id": agent_id,
            "version": version,
            "system_prompt": system_prompt,
            "allowed_tools": json.dumps(allowed_tools),
            "skills_dir": skills_dir,
            "mcp_server_ids": None if mcp_server_ids is None else json.dumps(mcp_server_ids),
            "model_overrides": json.dumps(model_overrides),
            "memory_namespace": memory_namespace,
            "created_by": created_by_user_id,
            "created_at": now,
        },
    ).lastrowid
    return int(version_id or 0)


def _row_to_version(row: dict[str, Any], active_version_id: int | None) -> AgentVersion:
    return AgentVersion(
        id=int(row["id"]),
        agent_id=int(row["agent_id"]),
        version=int(row["version"]),
        system_prompt=str(row["system_prompt"]),
        allowed_tools=json.loads(row["allowed_tools"]),
        skills_dir=row["skills_dir"],
        mcp_server_ids=None if row["mcp_server_ids"] is None else json.loads(row["mcp_server_ids"]),
        model_overrides=json.loads(row["model_overrides"]) if row["model_overrides"] else {},
        memory_namespace=str(row["memory_namespace"]),
        created_at=str(row["created_at"]),
        is_active=int(row["id"]) == active_version_id,
    )


def _get_agent_row(db: SQLiteDatabase, name: str) -> dict[str, Any] | None:
    return db.execute(
        f"SELECT {_AGENT_ROW_COLUMNS} FROM agents WHERE name = :name",
        {"name": name},
    ).fetchone()


def get_by_name(name: str) -> Agent | None:
    """Return the agent: runtime fields from its active version, caps from the row."""
    db = _db()
    agent = _get_agent_row(db, name)
    if agent is None:
        return None
    version = db.execute(
        "SELECT * FROM agent_versions WHERE id = :vid",
        {"vid": agent["active_version_id"]},
    ).fetchone()
    if version is None:
        return None
    return Agent(
        id=int(agent["id"]),
        name=str(agent["name"]),
        system_prompt=str(version["system_prompt"]),
        allowed_tools=json.loads(version["allowed_tools"]),
        active_version_id=int(agent["active_version_id"]),
        tenant_id=str(agent["tenant_id"]) if agent["tenant_id"] is not None else "default",
        team_id=str(agent["team_id"]) if agent["team_id"] is not None else None,
        skills_dir=version["skills_dir"],
        mcp_server_ids=(
            None if version["mcp_server_ids"] is None else json.loads(version["mcp_server_ids"])
        ),
        model_overrides=json.loads(version["model_overrides"])
        if version["model_overrides"]
        else {},
        memory_namespace=str(version["memory_namespace"]),
        **_parse_caps(agent),
    )


def create_version(
    name: str,
    *,
    system_prompt: Any = _UNSET,
    allowed_tools: Any = _UNSET,
    skills_dir: Any = _UNSET,
    mcp_server_ids: Any = _UNSET,
    model_overrides: Any = _UNSET,
    memory_namespace: Any = _UNSET,
    activate: bool = True,
    created_by_user_id: str | None = None,
) -> AgentVersion:
    """Snapshot a new version: copy the active version, override provided fields."""
    db = _db()
    now = _now()
    with db.transaction() as conn:
        agent = conn.execute(
            "SELECT id, active_version_id FROM agents WHERE name = :name", {"name": name}
        ).fetchone()
        if agent is None:
            raise ValueError(f"agent {name!r} not found")
        agent_id = int(agent["id"])
        base = conn.execute(
            "SELECT * FROM agent_versions WHERE id = :vid", {"vid": agent["active_version_id"]}
        ).fetchone()
        if base is None:
            raise ValueError(f"agent {name!r} has no active version")
        max_row = conn.execute(
            "SELECT MAX(version) AS m FROM agent_versions WHERE agent_id = :aid",
            {"aid": agent_id},
        ).fetchone()
        assert max_row is not None  # aggregate always returns a row
        next_version = int(max_row["m"]) + 1

        merged = _merge_version_fields(
            base,
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            skills_dir=skills_dir,
            mcp_server_ids=mcp_server_ids,
            model_overrides=model_overrides,
            memory_namespace=memory_namespace,
        )
        version_id = _insert_version(
            conn,
            agent_id=agent_id,
            version=next_version,
            now=now,
            created_by_user_id=created_by_user_id,
            **merged,
        )
        if activate:
            conn.execute(
                "UPDATE agents SET active_version_id = :vid WHERE id = :aid",
                {"vid": version_id, "aid": agent_id},
            )
        active_id = version_id if activate else int(agent["active_version_id"])
        row = conn.execute(
            "SELECT * FROM agent_versions WHERE id = :vid", {"vid": version_id}
        ).fetchone()
        assert row is not None  # just inserted
    return _row_to_version(row, active_id)


def _merge_version_fields(
    base: dict[str, Any],
    *,
    system_prompt: Any,
    allowed_tools: Any,
    skills_dir: Any,
    mcp_server_ids: Any,
    model_overrides: Any,
    memory_namespace: Any,
) -> dict[str, Any]:
    return {
        "system_prompt": str(base["system_prompt"]) if system_prompt is _UNSET else system_prompt,
        "allowed_tools": (
            json.loads(base["allowed_tools"]) if allowed_tools is _UNSET else allowed_tools
        ),
        "skills_dir": base["skills_dir"] if skills_dir is _UNSET else skills_dir,
        "mcp_server_ids": (
            (None if base["mcp_server_ids"] is None else json.loads(base["mcp_server_ids"]))
            if mcp_server_ids is _UNSET
            else mcp_server_ids
        ),
        "model_overrides": (
            (json.loads(base["model_overrides"]) if base["model_overrides"] else {})
            if model_overrides is _UNSET
            else model_overrides
        ),
        "memory_namespace": (
            str(base["memory_namespace"]) if memory_namespace is _UNSET else memory_namespace
        ),
    }


def delete_agent(name: str) -> bool:
    """Hard-delete an agent and all its versions in one transaction.

    Returns True when an agent was removed, False when no such agent exists.
    Deletes ``agent_versions`` before ``agents`` to respect the FK ordering.
    """
    db = _db()
    with db.transaction() as conn:
        agent = conn.execute("SELECT id FROM agents WHERE name = :name", {"name": name}).fetchone()
        if agent is None:
            return False
        agent_id = int(agent["id"])
        conn.execute(
            "DELETE FROM agent_mcp_server_bindings WHERE agent_id = :aid",
            {"aid": agent_id},
        )
        conn.execute(
            "DELETE FROM agent_oauth_bindings WHERE agent_id = :aid",
            {"aid": agent_id},
        )
        # Detach the active-version FK before removing version rows.
        conn.execute(
            "UPDATE agents SET active_version_id = NULL WHERE id = :aid", {"aid": agent_id}
        )
        conn.execute("DELETE FROM agent_versions WHERE agent_id = :aid", {"aid": agent_id})
        conn.execute("DELETE FROM agents WHERE id = :aid", {"aid": agent_id})
    return True


def activate_version(name: str, version: int) -> None:
    db = _db()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT av.id FROM agent_versions av JOIN agents a ON a.id = av.agent_id "
            "WHERE a.name = :name AND av.version = :version",
            {"name": name, "version": version},
        ).fetchone()
        if row is None:
            raise ValueError(f"agent {name!r} has no version {version}")
        conn.execute(
            "UPDATE agents SET active_version_id = :vid WHERE name = :name",
            {"vid": row["id"], "name": name},
        )


def list_versions(name: str) -> list[AgentVersion]:
    db = _db()
    agent = _get_agent_row(db, name)
    if agent is None:
        return []
    rows = db.execute(
        "SELECT * FROM agent_versions WHERE agent_id = :aid ORDER BY version DESC",
        {"aid": agent["id"]},
    ).fetchall()
    return [_row_to_version(row, agent["active_version_id"]) for row in rows]


def get_by_name_version(name: str, version: int) -> AgentVersion | None:
    db = _db()
    agent = _get_agent_row(db, name)
    if agent is None:
        return None
    row = db.execute(
        "SELECT * FROM agent_versions WHERE agent_id = :aid AND version = :version",
        {"aid": agent["id"], "version": version},
    ).fetchone()
    if row is None:
        return None
    return _row_to_version(row, agent["active_version_id"])


def get_version_by_id(version_id: int) -> AgentVersion | None:
    db = _db()
    row = db.execute(
        "SELECT av.*, a.active_version_id AS agent_active "
        "FROM agent_versions av JOIN agents a ON a.id = av.agent_id WHERE av.id = :vid",
        {"vid": version_id},
    ).fetchone()
    if row is None:
        return None
    return _row_to_version(row, row["agent_active"])


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


def get_agent_for_user(user_id: str) -> Agent | None:
    db = _db()
    row = db.execute(
        "SELECT a.name FROM agents a JOIN user_agents ua ON ua.agent_id = a.id "
        "WHERE ua.user_id = :user_id LIMIT 1",
        {"user_id": user_id},
    ).fetchone()
    if row is None:
        return None
    return get_by_name(str(row["name"]))


def assign_channel(platform: str, channel_id: str, agent_id: int) -> None:
    db = _db()
    active = db.execute(
        "SELECT active_version_id FROM agents WHERE id = :aid", {"aid": agent_id}
    ).fetchone()
    bound_version_id = active["active_version_id"] if active else None
    db.execute(
        "INSERT OR REPLACE INTO channel_agents "
        "(platform, channel_id, agent_id, bound_version_id, created_at) "
        "VALUES (:platform, :channel_id, :agent_id, :bound_version_id, :created_at)",
        {
            "platform": platform,
            "channel_id": channel_id,
            "agent_id": agent_id,
            "bound_version_id": bound_version_id,
            "created_at": _now(),
        },
    )


def unassign_channel(platform: str, channel_id: str) -> None:
    _db().execute(
        "DELETE FROM channel_agents WHERE platform = :platform AND channel_id = :channel_id",
        {"platform": platform, "channel_id": channel_id},
    )


def get_agent_for_channel(platform: str, channel_id: str) -> Agent | None:
    db = _db()
    row = db.execute(
        "SELECT a.name FROM agents a JOIN channel_agents ca ON ca.agent_id = a.id "
        "WHERE ca.platform = :platform AND ca.channel_id = :channel_id LIMIT 1",
        {"platform": platform, "channel_id": channel_id},
    ).fetchone()
    if row is None:
        return None
    return get_by_name(str(row["name"]))


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


def list_channels_for_agent(agent_id: int) -> list[dict[str, Any]]:
    rows = (
        _db()
        .execute(
            "SELECT platform, channel_id, bound_version_id FROM channel_agents "
            "WHERE agent_id = :agent_id ORDER BY platform, channel_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [
        {
            "platform": str(row["platform"]),
            "channel_id": str(row["channel_id"]),
            "bound_version_id": row["bound_version_id"],
        }
        for row in rows
    ]


def bind_mcp_server(agent_id: int, server_id: str, created_by: str | None = None) -> None:
    _db().execute(
        "INSERT OR IGNORE INTO agent_mcp_server_bindings "
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
        "DELETE FROM agent_mcp_server_bindings "
        "WHERE agent_id = :agent_id AND server_id = :server_id",
        {"agent_id": agent_id, "server_id": server_id},
    )


def list_mcp_servers_for_agent(agent_id: int) -> list[str]:
    rows = (
        _db()
        .execute(
            "SELECT server_id FROM agent_mcp_server_bindings "
            "WHERE agent_id = :agent_id ORDER BY server_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [str(row["server_id"]) for row in rows]


def get_channel_bound_version_id(platform: str, channel_id: str) -> int | None:
    row = (
        _db()
        .execute(
            "SELECT bound_version_id FROM channel_agents "
            "WHERE platform = :platform AND channel_id = :channel_id",
            {"platform": platform, "channel_id": channel_id},
        )
        .fetchone()
    )
    if row is None or row["bound_version_id"] is None:
        return None
    return int(row["bound_version_id"])


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
