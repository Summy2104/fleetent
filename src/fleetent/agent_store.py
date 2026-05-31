import datetime
import json
from dataclasses import dataclass, field
from typing import Any

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]
    # Extensible per-agent capability switches (SB3 owner). Currently carries
    # `code_execution: bool | None`; SB5 reuses the same JSON column for
    # `sandbox_env`. Stored as a JSON TEXT column, mirroring `allowed_tools`.
    features: dict[str, Any] = field(default_factory=dict)


def create_agent(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    features: dict[str, Any] | None = None,
) -> Agent:
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    features = features or {}
    with _conn() as conn:
        cursor = conn.execute(
            "INSERT INTO agents (name, system_prompt, allowed_tools, features, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, system_prompt, json.dumps(allowed_tools), json.dumps(features), now),
        )
        agent_id = cursor.lastrowid
    assert agent_id is not None
    return Agent(
        id=agent_id,
        name=name,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        features=features,
    )


_SELECT_COLS = "id, name, system_prompt, allowed_tools, features"


def _join_cols(alias: str) -> str:
    """Qualify `_SELECT_COLS` with a table alias for JOIN queries."""
    return ", ".join(f"{alias}.{c.strip()}" for c in _SELECT_COLS.split(","))


def _row_to_agent(row: tuple[Any, ...]) -> Agent:
    return Agent(
        id=row[0],
        name=row[1],
        system_prompt=row[2],
        allowed_tools=json.loads(row[3]),
        # `or "{}"` guards a legacy row whose features value is NULL.
        features=json.loads(row[4] or "{}"),
    )


def get_by_name(name: str) -> Agent | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(f"SELECT {_SELECT_COLS} FROM agents WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return _row_to_agent(row)


def assign_user(user_id: str, agent_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_agents (user_id, agent_id) VALUES (?, ?)",
            (user_id, agent_id),
        )


def get_agent_for_user(user_id: str) -> Agent | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"""SELECT {_join_cols("a")}
               FROM agents a
               JOIN user_agents ua ON ua.agent_id = a.id
               WHERE ua.user_id = ?
               LIMIT 1""",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_agent(row)


def assign_channel(platform: str, channel_id: str, agent_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO channel_agents (platform, channel_id, agent_id, created_at)"
            " VALUES (?, ?, ?, ?)",
            (platform, channel_id, agent_id, datetime.datetime.now(datetime.UTC).isoformat()),
        )


def unassign_channel(platform: str, channel_id: str) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            "DELETE FROM channel_agents WHERE platform = ? AND channel_id = ?",
            (platform, channel_id),
        )


def get_agent_for_channel(platform: str, channel_id: str) -> Agent | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"""SELECT {_join_cols("ca_a")}
               FROM agents ca_a
               JOIN channel_agents ca ON ca.agent_id = ca_a.id
               WHERE ca.platform = ? AND ca.channel_id = ?
               LIMIT 1""",
            (platform, channel_id),
        ).fetchone()
    if not row:
        return None
    return _row_to_agent(row)


def _get_default_agent_name() -> str | None:
    from fleetent.config import Settings

    return Settings().default_agent_name


def get_default_agent() -> Agent | None:
    name = _get_default_agent_name()
    if not name:
        return None
    return get_by_name(name)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            # `features` is created inline here so fresh / test (tmp_path) DBs
            # always carry it. Per the zy override, existing production DBs are
            # upgraded by alembic migration 002 (op.add_column), NOT a runtime
            # PRAGMA+ALTER in _init_db. See docs/capabilities/wave2-apply-decisions.md.
            """CREATE TABLE IF NOT EXISTS agents (
                id             INTEGER PRIMARY KEY,
                name           TEXT UNIQUE NOT NULL,
                system_prompt  TEXT NOT NULL,
                allowed_tools  TEXT NOT NULL,
                features       TEXT,
                created_at     TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_agents (
                user_id   TEXT NOT NULL,
                agent_id  INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS channel_agents (
                id         INTEGER PRIMARY KEY,
                platform   TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                agent_id   INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(platform, channel_id)
            )"""
        )
