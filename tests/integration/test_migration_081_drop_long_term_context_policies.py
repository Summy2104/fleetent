"""Integration tests for dropping the dormant long-term context policy table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")
_TABLE_NAME = "long_term_context_" "policies"


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _upgrade(db: Path, rev: str = "head") -> None:
    command.upgrade(_cfg(db), rev)


def _tables(db: Path) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_upgrade_head_drops_dormant_context_policy_table(tmp_path: Path) -> None:
    db = tmp_path / "management.db"

    _upgrade(db)

    assert _TABLE_NAME not in _tables(db)


def test_upgrade_from_080_drops_existing_dormant_context_policy_rows(tmp_path: Path) -> None:
    db = tmp_path / "management.db"
    _upgrade(db, "080")

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO __TABLE__ (
                id,
                tenant_id,
                agent_id,
                user_memory_enabled,
                tenant_shared_memory_enabled,
                team_shared_memory_enabled,
                knowledge_base_enabled,
                user_memory_max_tokens,
                user_memory_top_k,
                tenant_shared_memory_max_tokens,
                tenant_shared_memory_top_k,
                team_shared_memory_max_tokens,
                team_shared_memory_top_k,
                knowledge_base_max_tokens,
                knowledge_base_top_k,
                conflict_preference,
                created_at,
                updated_at
            ) VALUES (
                'policy-1',
                'default',
                NULL,
                1,
                0,
                0,
                1,
                400,
                5,
                0,
                0,
                0,
                0,
                300,
                4,
                'user_memory',
                '2026-06-01T00:00:00+00:00',
                '2026-06-01T00:00:00+00:00'
            )
            """.replace("__TABLE__", _TABLE_NAME)
        )
        conn.commit()

    _upgrade(db)

    assert _TABLE_NAME not in _tables(db)
