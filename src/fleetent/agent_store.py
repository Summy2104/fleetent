"""Agent definitions, immutable version snapshots, and user/channel bindings.

Schema lifecycle is owned by Alembic (see migrations 001 and 027). This store
reads and writes through the shared DB runtime boundary using named parameters;
it never creates schema. The runtime-facing fields (system_prompt, allowed_tools,
skills_dir, mcp_server_ids, model_overrides, memory_namespace) live in
``agent_versions``; ``agents.active_version_id`` points at the active snapshot.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteConnection, SQLiteDatabase, create_database

_UNSET: Any = object()


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]
    active_version_id: int | None = None


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
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_agent(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    *,
    skills_dir: str | None = None,
    mcp_server_ids: list[str] | None = None,
    model_overrides: dict[str, Any] | None = None,
    memory_namespace: str = "default",
) -> Agent:
    """Create an agent plus its version-1 snapshot in a single transaction."""
    db = _db()
    now = _now()
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM agents WHERE name = :name", {"name": name}).fetchone():
            raise ValueError(f"agent {name!r} already exists")
        agent_id = conn.execute(
            "INSERT INTO agents (name, system_prompt, allowed_tools, created_at) "
            "VALUES (:name, :system_prompt, :allowed_tools, :created_at)",
            {
                "name": name,
                "system_prompt": system_prompt,
                "allowed_tools": json.dumps(allowed_tools),
                "created_at": now,
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
    )


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
        "SELECT id, name, active_version_id FROM agents WHERE name = :name",
        {"name": name},
    ).fetchone()


def get_by_name(name: str) -> Agent | None:
    """Return the agent with runtime fields unpacked from its active version."""
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


def assign_user(user_id: str, agent_id: int) -> None:
    _db().execute(
        "INSERT OR IGNORE INTO user_agents (user_id, agent_id) VALUES (:user_id, :agent_id)",
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
    return Settings(anthropic_api_key="").default_agent_name


def get_default_agent() -> Agent | None:
    name = _get_default_agent_name()
    if not name:
        return None
    return get_by_name(name)
