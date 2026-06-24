"""Cron e2e helpers — exclusively owned by e2e-sandbox-cron change.

Design (task 1.3 probe conclusions):
- CronScheduler.start() loads pre-existing agent_state.db rows at boot — pre-seeding
  is the only reliable cross-process task injection path.
- SchedulingSettings.enabled defaults True → any standalone agent boots the scheduler.
- agent_state.db physical path: agent_home / "data" / "agent_state.db".
- task_type="notify", deliver=None, origin=None → _deliver() returns None (no connector
  error), _record_run writes last_status="ok" unconditionally — no LLM needed.
- user_id="default" → _resolve_cron_principal short-circuits, no management DB needed.
"""

from __future__ import annotations

import sqlite3
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from fleetent import agent_config
from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    running_process,
    wait_for_http_ready,
)

_AGENT_NAME = "cron-probe"
_INTERVAL_SECONDS = 2
_FIRE_TIMEOUT = 20.0


@dataclass(frozen=True)
class CronProbe:
    state_db_path: Path
    task_id: str


def _write_agent_yaml(agent_home: Path) -> None:
    data = {
        "name": _AGENT_NAME,
        "version": 1,
        "system_prompt": "Cron e2e probe agent.",
        "models": agent_config.default_models().model_dump(mode="json"),
        # scheduling.enabled defaults True in SchedulingSettings — explicit for clarity
        "scheduling": {"enabled": True},
    }
    (agent_home / "agent.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _create_state_db(db_path: Path) -> str:
    """Apply all agent_state.db migrations and insert a pre-seeded interval notify task."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    db_path.parent.mkdir(parents=True, exist_ok=True)
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, sql in MIGRATIONS:
            if version > current:
                conn.executescript(sql)
                conn.execute(f"PRAGMA user_version = {version}")
                conn.commit()
                current = version

        conn.execute(
            "INSERT INTO scheduled_tasks "
            "(id, name, cron_expr, schedule_kind, interval_seconds, timezone, "
            "user_id, message, source, enabled, created_at, "
            "last_run_at, last_status, last_error, next_run_at, "
            "session_id, deliver, origin, task_type, notify_text) "
            "VALUES "
            "(:id, :name, NULL, 'interval', :secs, 'UTC', "
            "'default', 'e2e probe', 'test', 1, :now, "
            "NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL, 'notify', 'cron-probe-fired')",
            {"id": task_id, "name": "e2e-cron-probe", "secs": _INTERVAL_SECONDS, "now": now},
        )
        conn.commit()
    finally:
        conn.close()
    return task_id


def _poll_run_state(db_path: Path, task_id: str) -> dict[str, object]:
    """Block until last_run_at is populated; return the row. Raises TimeoutError."""
    deadline = time.monotonic() + _FIRE_TIMEOUT
    while time.monotonic() < deadline:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, last_run_at, last_status, last_error FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            conn.close()
            if row and row["last_run_at"] is not None:
                return dict(row)
        except sqlite3.OperationalError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"cron task {task_id} did not fire within {_FIRE_TIMEOUT}s (db={db_path})")


@pytest.fixture
def cron_probe(tmp_path: Path) -> Iterator[CronProbe]:
    """Standalone scheduling agent with a pre-seeded 2-second interval notify task."""
    # Directory name must match agent name in agent.yaml (scan_home validation)
    agent_home = tmp_path / _AGENT_NAME
    agent_home.mkdir()
    fleetent_home = tmp_path / "cron-home"
    fleetent_home.mkdir()

    state_db_path = agent_home / "data" / "agent_state.db"

    _write_agent_yaml(agent_home)
    task_id = _create_state_db(state_db_path)

    port = reserve_port()
    env = child_env(
        extra={
            "FLEETENT_HOME": str(fleetent_home),
            # Notify tasks never call the LLM; placeholder key prevents startup errors
            "OPENAI_API_KEY": "sk-cron-e2e-stub",
        }
    )
    argv = [
        sys.executable,
        "-m",
        "fleetent",
        "agent",
        "run",
        _AGENT_NAME,
        "--home",
        str(agent_home),
        "--port",
        str(port),
    ]

    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_http_ready(proc, f"http://127.0.0.1:{port}/health", timeout=20.0)
        yield CronProbe(state_db_path=state_db_path, task_id=task_id)
