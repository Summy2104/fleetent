"""Async task + streamed-log + workspace persistence for the askit console.

db runtime + named params, no ORM. Schema owned by migration 017. Per-workspace
serialization for write operations is provided by workspace_lock().
"""

import asyncio
import datetime
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_locks: dict[str, asyncio.Lock] = {}


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


@asynccontextmanager
async def workspace_lock(workspace: str) -> AsyncIterator[None]:
    """Serialize write operations within one workspace (read-only ops need not use it)."""
    lock = _locks.setdefault(workspace or "_default", asyncio.Lock())
    async with lock:
        yield


def create_task(
    series: str,
    command: str,
    *,
    params: dict[str, Any] | None = None,
    workspace: str | None = None,
    env: str | None = None,
    created_by: str | None = None,
) -> str:
    tid = uuid.uuid4().hex[:12]
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO askit_tasks
                (id, series, command, params, workspace, env, status, created_by,
                 created_at, updated_at)
            VALUES (:id, :series, :command, :params, :workspace, :env, 'queued', :created_by,
                    :created_at, :updated_at)
            """,
            {
                "id": tid,
                "series": series,
                "command": command,
                "params": json.dumps(params or {}),
                "workspace": workspace,
                "env": env,
                "created_by": created_by,
                "created_at": now,
                "updated_at": now,
            },
        )
    return tid


def finish_task(
    task_id: str, status: str, exit_code: int | None, artifact: str | None = None
) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "UPDATE askit_tasks SET status = :status, exit_code = :exit_code, "
            "artifact = :artifact, updated_at = :now WHERE id = :id",
            {
                "status": status,
                "exit_code": exit_code,
                "artifact": artifact,
                "now": _now(),
                "id": task_id,
            },
        )


def append_log(task_id: str, seq: int, stream: str, line: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO askit_task_logs (task_id, seq, stream, line) "
            "VALUES (:task_id, :seq, :stream, :line)",
            {"task_id": task_id, "seq": seq, "stream": stream, "line": line},
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    row = (
        _database().execute("SELECT * FROM askit_tasks WHERE id = :id", {"id": task_id}).fetchone()
    )
    if row is None:
        return None
    out = dict(row)
    out["params"] = json.loads(out["params"]) if out.get("params") else {}
    return out


def get_logs(task_id: str) -> list[dict[str, Any]]:
    return (
        _database()
        .execute(
            "SELECT seq, stream, line FROM askit_task_logs WHERE task_id = :id ORDER BY seq",
            {"id": task_id},
        )
        .fetchall()
    )


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    return (
        _database()
        .execute(
            "SELECT id, series, command, status, exit_code, updated_at FROM askit_tasks "
            "ORDER BY created_at DESC LIMIT :limit",
            {"limit": limit},
        )
        .fetchall()
    )


def add_workspace(env: str, repo_path: str, endpoint: str | None = None) -> str:
    wid = uuid.uuid4().hex[:12]
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO askit_workspaces (id, env, repo_path, endpoint, created_at) "
            "VALUES (:id, :env, :repo_path, :endpoint, :now)",
            {"id": wid, "env": env, "repo_path": repo_path, "endpoint": endpoint, "now": _now()},
        )
    return wid
