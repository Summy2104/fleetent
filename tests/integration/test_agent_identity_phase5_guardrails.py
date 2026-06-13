from pathlib import Path

import yaml

import fleetent.agent_store as agent_store
from fleetent.platform.agent_lifecycle import materialize
from tests.integration._migration_template import apply_migrations


def _management_columns(db_path: Path) -> dict[str, set[str]]:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        return {
            table: {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for table in tables
        }


def test_management_tables_store_agent_relationships_by_agent_id_only(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    columns = _management_columns(db_path)

    offenders = sorted(table for table, cols in columns.items() if table != "agents" and "agent_name" in cols)
    assert offenders == []


def test_materialize_writes_agent_name_identity_to_home(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    agent = agent_store.create_agent("support", "You are support.", [])

    home = materialize.write_home(materialize.agent_file_from_store(agent))
    agent_doc = yaml.safe_load((home / "agent.yaml").read_text(encoding="utf-8"))

    assert home == materialize.home_dir("support")
    assert agent_doc["name"] == "support"
    assert "agent_id" not in (home / "agent.yaml").read_text(encoding="utf-8")
