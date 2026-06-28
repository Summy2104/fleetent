"""Integration tests for retiring agent versioning and askit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store
from fleetent.platform.agent_lifecycle import materialize
from fleetent.node.reconcile import _config_hash


def _config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _legacy_agent(conn: sqlite3.Connection, name: str) -> agent_store.Agent:
    row = conn.execute(
        """
        SELECT
            a.id,
            a.name,
            a.active_version_id,
            a.features,
            a.plugins,
            a.allowed_skills,
            a.tenant_id,
            a.team_id,
            a.icon,
            a.config_overrides,
            a.supports_dm,
            a.supports_groups,
            av.version,
            av.system_prompt,
            av.allowed_tools,
            av.skills_dir,
            av.model_overrides,
            av.memory_namespace
        FROM agents a
        JOIN agent_versions av ON av.id = a.active_version_id
        WHERE a.name = ?
        """,
        (name,),
    ).fetchone()
    assert row is not None
    return agent_store.Agent(
        id=int(row["id"]),
        name=str(row["name"]),
        version=int(row["version"]),
        system_prompt=str(row["system_prompt"]),
        allowed_tools=json.loads(row["allowed_tools"]),
        features=json.loads(row["features"] or "{}"),
        plugins=json.loads(row["plugins"] or "[]"),
        allowed_skills=json.loads(row["allowed_skills"] or "[]"),
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] is not None else "default",
        team_id=str(row["team_id"]) if row["team_id"] is not None else None,
        skills_dir=row["skills_dir"],
        mcp_server_ids=None,
        model_overrides=json.loads(row["model_overrides"] or "{}"),
        memory_namespace=str(row["memory_namespace"]),
        icon=row["icon"],
        config_overrides=json.loads(row["config_overrides"] or "{}"),
        supports_dm=bool(row["supports_dm"]),
        supports_groups=bool(row["supports_groups"]),
    )


def _agent_from_agents_row(conn: sqlite3.Connection, name: str) -> agent_store.Agent:
    row = conn.execute(
        """
        SELECT
            id,
            name,
            version,
            system_prompt,
            allowed_tools,
            model_overrides,
            memory_namespace,
            skills_dir,
            features,
            plugins,
            allowed_skills,
            tenant_id,
            team_id,
            icon,
            config_overrides,
            supports_dm,
            supports_groups
        FROM agents
        WHERE name = ?
        """,
        (name,),
    ).fetchone()
    assert row is not None
    return agent_store.Agent(
        id=int(row["id"]),
        name=str(row["name"]),
        version=int(row["version"]),
        system_prompt=str(row["system_prompt"]),
        allowed_tools=json.loads(row["allowed_tools"]),
        features=json.loads(row["features"] or "{}"),
        plugins=json.loads(row["plugins"] or "[]"),
        allowed_skills=json.loads(row["allowed_skills"] or "[]"),
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] is not None else "default",
        team_id=str(row["team_id"]) if row["team_id"] is not None else None,
        skills_dir=row["skills_dir"],
        mcp_server_ids=None,
        model_overrides=json.loads(row["model_overrides"] or "{}"),
        memory_namespace=str(row["memory_namespace"]),
        icon=row["icon"],
        config_overrides=json.loads(row["config_overrides"] or "{}"),
        supports_dm=bool(row["supports_dm"]),
        supports_groups=bool(row["supports_groups"]),
    )


def _payload_hash(agent: agent_store.Agent) -> str:
    payload = materialize.desired_state_payload_from_agent_file(materialize.agent_file_from_store(agent))
    return _config_hash(payload)


def _seed_agent_versions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO agents (
            id, name, system_prompt, allowed_tools, created_at, tenant_id, team_id,
            features, plugins, allowed_skills, icon, config_overrides, supports_dm, supports_groups
        )
        VALUES (
            1, 'ops', 'stale prompt', '["legacy"]', '2026-06-28T00:00:00+00:00', 'default', NULL,
            '{"code_execution": true}', '["plugin-a"]', '["billing"]', ':ops:',
            '{"im":{"supports_dm":true}}', 1, 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agent_versions (
            id, agent_id, version, system_prompt, allowed_tools, skills_dir,
            mcp_server_ids, model_overrides, memory_namespace, created_at
        )
        VALUES
            (
                10, 1, 1, 'old prompt', '["shell"]', 'agents/ops/v1', '["docs"]',
                '{"routes": {}}', 'ops-v1', '2026-06-28T00:00:00+00:00'
            ),
            (
                11, 1, 2, 'live prompt', '["shell","docs__*"]', 'agents/ops/live', '["docs","github"]',
                '{"routes": {}}', 'ops-live', '2026-06-28T01:00:00+00:00'
            )
        """
    )
    conn.execute("UPDATE agents SET active_version_id = 11 WHERE id = 1")
    conn.execute(
        """
        INSERT INTO agent_mcp_servers (agent_id, server_id, created_at)
        VALUES
            (1, 'docs', '2026-06-28T01:00:00+00:00'),
            (1, 'github', '2026-06-28T01:00:00+00:00')
        """
    )
    conn.commit()


def test_head_backfills_runtime_fields_into_agents(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    command.upgrade(_config(db), "104")

    with sqlite3.connect(db) as conn:
        _seed_agent_versions(conn)

    command.upgrade(_config(db), "head")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(agents)")}
        row = conn.execute(
            """
            SELECT version, system_prompt, allowed_tools, model_overrides, memory_namespace, skills_dir
            FROM agents
            WHERE id = 1
            """
        ).fetchone()

    assert {"version", "model_overrides", "memory_namespace", "skills_dir"} <= cols
    assert row is not None
    assert row["version"] == 2
    assert row["system_prompt"] == "live prompt"
    assert json.loads(row["allowed_tools"]) == ["shell", "docs__*"]
    assert json.loads(row["model_overrides"]) == {"routes": {}}
    assert row["memory_namespace"] == "ops-live"
    assert row["skills_dir"] == "agents/ops/live"


def test_head_preserves_desired_state_config_hash_after_backfill(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    command.upgrade(_config(db), "104")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        _seed_agent_versions(conn)
        before_hash = _payload_hash(_legacy_agent(conn, "ops"))

    command.upgrade(_config(db), "head")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        after_hash = _payload_hash(_agent_from_agents_row(conn, "ops"))

    assert after_hash == before_hash
