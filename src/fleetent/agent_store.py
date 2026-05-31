import datetime
import json
from dataclasses import dataclass
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
    # opt-in skill whitelist (fnmatch); None = not declared → no skill injected.
    allowed_skills: list[str] | None = None
    # fnmatch patterns excluded after the whitelist hits; None/[] = no exclusion.
    blocked_skills: list[str] | None = None


def _dump_opt(value: list[str] | None) -> str | None:
    """JSON-encode an optional skill list, preserving None as SQL NULL."""
    return None if value is None else json.dumps(value)


def _load_opt(value: str | None) -> list[str] | None:
    """Decode an optional skill list column, mapping SQL NULL back to None."""
    if value is None:
        return None
    result: list[str] = json.loads(value)
    return result


def create_agent(
    name: str,
    system_prompt: str,
    allowed_tools: list[str],
    allowed_skills: list[str] | None = None,
    blocked_skills: list[str] | None = None,
) -> Agent:
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        cursor = conn.execute(
            "INSERT INTO agents"
            " (name, system_prompt, allowed_tools, allowed_skills, blocked_skills, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                name,
                system_prompt,
                json.dumps(allowed_tools),
                _dump_opt(allowed_skills),
                _dump_opt(blocked_skills),
                now,
            ),
        )
        agent_id = cursor.lastrowid
    assert agent_id is not None
    return Agent(
        id=agent_id,
        name=name,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        allowed_skills=allowed_skills,
        blocked_skills=blocked_skills,
    )


_SELECT_COLS = "id, name, system_prompt, allowed_tools, allowed_skills, blocked_skills"


def _join_cols(alias: str) -> str:
    """Qualify `_SELECT_COLS` with a table alias for JOIN queries."""
    return ", ".join(f"{alias}.{c.strip()}" for c in _SELECT_COLS.split(","))


def _row_to_agent(row: tuple[Any, ...]) -> Agent:
    return Agent(
        id=row[0],
        name=row[1],
        system_prompt=row[2],
        allowed_tools=json.loads(row[3]),
        allowed_skills=_load_opt(row[4]),
        blocked_skills=_load_opt(row[5]),
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


def _ensure_skill_columns(conn: Any) -> None:
    """Backfill the agent-skill-binding columns on a pre-existing agents table.

    The `agents` table may already exist from the alembic 001 migration (or the
    legacy schema) without the skill columns. SQLite has no IF NOT EXISTS for
    ADD COLUMN, so probe `table_info` and add only what is missing — idempotent
    and safe to run on every `_init_db()` call.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)")}
    if "allowed_skills" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN allowed_skills TEXT")
    if "blocked_skills" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN blocked_skills TEXT")


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agents (
                id             INTEGER PRIMARY KEY,
                name           TEXT UNIQUE NOT NULL,
                system_prompt  TEXT NOT NULL,
                allowed_tools  TEXT NOT NULL,
                allowed_skills TEXT,
                blocked_skills TEXT,
                created_at     TEXT NOT NULL
            )"""
        )
        _ensure_skill_columns(conn)
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
