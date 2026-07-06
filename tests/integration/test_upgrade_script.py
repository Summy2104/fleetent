import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "upgrade.py"


def _load_upgrade_module():
    spec = importlib.util.spec_from_file_location("_upgrade_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_drop_im_outbound_queue_tables_removes_table_from_agent_dbs(tmp_path):
    """agent-hosted-im (Group 6.5): the queue table is dropped on upgrade (full cutover)."""
    upgrade = _load_upgrade_module()

    # An agent-side DB that still carries the legacy queue table + an unrelated table.
    agent_db = tmp_path / "tenants" / "acme" / "agents" / "support" / "data" / "agent_state.db"
    agent_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(agent_db)
    conn.execute("CREATE TABLE im_outbound_queue (id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("CREATE TABLE traces (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    dropped = upgrade.drop_im_outbound_queue_tables(tmp_path)

    assert agent_db in dropped
    conn = sqlite3.connect(agent_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "im_outbound_queue" not in tables
    assert "traces" in tables  # unrelated tables are untouched


def test_drop_im_outbound_queue_tables_is_noop_when_absent(tmp_path):
    upgrade = _load_upgrade_module()

    agent_db = tmp_path / "data" / "agent_state.db"
    agent_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(agent_db)
    conn.execute("CREATE TABLE traces (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    dropped = upgrade.drop_im_outbound_queue_tables(tmp_path)

    assert dropped == []


def test_dry_run_subprocess_uses_tmp_database_without_touching_repo_data(tmp_path):
    database_path = tmp_path / "fleetent.db"
    backup_root = tmp_path / "backups"
    repo_data_backups = REPO_ROOT / "data" / "backups"
    before = set(repo_data_backups.glob("*/fleetent.db")) if repo_data_backups.exists() else set()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            f"sqlite:///{database_path}",
            "--backup-dir",
            str(backup_root),
            "--dry-run",
        ],
        check=False,
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    after = set(repo_data_backups.glob("*/fleetent.db")) if repo_data_backups.exists() else set()
    assert result.returncode == 0
    assert str(database_path) in result.stdout
    assert "alembic upgrade head" in result.stdout
    assert not backup_root.exists()
    assert after == before


def test_backup_only_subprocess_creates_restorable_backup_in_tmp_path(tmp_path):
    database_path = tmp_path / "fleetent.db"
    database_path.write_bytes(b"restorable database")
    backup_root = tmp_path / "backups"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--backup-dir",
            str(backup_root),
            "--backup-only",
        ],
        check=False,
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    backups = list(backup_root.glob("*/fleetent.db"))
    assert result.returncode == 0
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"restorable database"
