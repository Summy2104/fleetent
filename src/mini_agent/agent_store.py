import datetime
import json
from dataclasses import dataclass

from mini_agent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from mini_agent.user_store import (
    _conn,
)


@dataclass
class Agent:
    id: int
    name: str
    system_prompt: str
    allowed_tools: list[str]


def create_agent(name: str, system_prompt: str, allowed_tools: list[str]) -> Agent:
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        cursor = conn.execute(
            "INSERT INTO agents (name, system_prompt, allowed_tools, created_at)"
            " VALUES (?, ?, ?, ?)",
            (name, system_prompt, json.dumps(allowed_tools), now),
        )
        agent_id = cursor.lastrowid
    assert agent_id is not None
    return Agent(id=agent_id, name=name, system_prompt=system_prompt, allowed_tools=allowed_tools)


def get_by_name(name: str) -> Agent | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, system_prompt, allowed_tools FROM agents WHERE name = ?", (name,)
        ).fetchone()
    if not row:
        return None
    return Agent(id=row[0], name=row[1], system_prompt=row[2], allowed_tools=json.loads(row[3]))


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
            """SELECT a.id, a.name, a.system_prompt, a.allowed_tools
               FROM agents a
               JOIN user_agents ua ON ua.agent_id = a.id
               WHERE ua.user_id = ?
               LIMIT 1""",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return Agent(id=row[0], name=row[1], system_prompt=row[2], allowed_tools=json.loads(row[3]))


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agents (
                id            INTEGER PRIMARY KEY,
                name          TEXT UNIQUE NOT NULL,
                system_prompt TEXT NOT NULL,
                allowed_tools TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_agents (
                user_id   TEXT NOT NULL,
                agent_id  INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_id)
            )"""
        )
