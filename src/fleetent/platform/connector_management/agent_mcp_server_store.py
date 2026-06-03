"""Per-agent MCP server definitions (migration 034, db runtime, named params, no ORM).

Each row is an agent-owned MCP server override. The global default layer lives in
``config/mcp.servers.yaml``; ``resolve_mcp_servers`` overlays agent-owned rows on top
of those defaults so an agent sees its own server set without leaking another agent's
connection or credentials.
"""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_COLS = (
    "agent_id, server_id, transport, url, auth_type, api_key_env, command, args, env, created_at"
)


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def add_mcp_server(
    agent_id: int | None,
    server_id: str,
    transport: str = "http",
    url: str = "",
    auth_type: str = "none",
    api_key_env: str = "",
    command: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> None:
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_mcp_servers
                (agent_id, server_id, transport, url, auth_type, api_key_env,
                 command, args, env, created_at)
            VALUES (:agent_id, :server_id, :transport, :url, :auth_type, :api_key_env,
                    :command, :args, :env, :created_at)
            """,
            {
                "agent_id": agent_id,
                "server_id": server_id,
                "transport": transport,
                "url": url,
                "auth_type": auth_type,
                "api_key_env": api_key_env,
                "command": command,
                "args": json.dumps(args) if args is not None else None,
                "env": json.dumps(env) if env is not None else None,
                "created_at": now,
            },
        )


def get_mcp_server(agent_id: int | None, server_id: str) -> dict[str, Any] | None:
    scope = "agent_id = :agent_id" if agent_id is not None else "agent_id IS NULL"
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM agent_mcp_servers WHERE server_id = :server_id AND {scope}",
            {"server_id": server_id, "agent_id": agent_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def list_mcp_servers(agent_id: int | None) -> list[dict[str, Any]]:
    scope = "agent_id = :agent_id" if agent_id is not None else "agent_id IS NULL"
    rows = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM agent_mcp_servers WHERE {scope} ORDER BY server_id",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return [_decode(r) for r in rows]


def resolve_mcp_servers(
    agent_id: int | None, defaults: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Overlay agent-owned servers on the global defaults, keyed by server id."""
    merged: dict[str, dict[str, Any]] = {d["id"]: dict(d) for d in defaults}
    for row in list_mcp_servers(agent_id):
        merged[row["server_id"]] = _as_server_config(row)
    return sorted(merged.values(), key=lambda s: s["id"])


def _as_server_config(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["server_id"],
        "transport": row["transport"],
        "url": row["url"],
        "auth_type": row["auth_type"],
        "api_key_env": row["api_key_env"],
        "command": row["command"],
        "args": row["args"] or [],
        "env": row["env"] or {},
    }


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["args"] = json.loads(out["args"]) if out.get("args") else []
    out["env"] = json.loads(out["env"]) if out.get("env") else {}
    return out
