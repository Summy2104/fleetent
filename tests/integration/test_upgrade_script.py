import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "upgrade.py"


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
