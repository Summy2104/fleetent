"""Behavioral tests for the one-click installer scripts/install.sh.

All runs are isolated to a temp HOME/CWD; they never touch the real ~/.fleetent
or repo data/. Steps that would hit the network (uv install, uv tool install,
alembic) are exercised only via no-side-effect paths (--help, unknown flag).
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install.sh"
SUPPORTED_FLAGS = ("--skip-db", "--skip-config", "--dir", "--help")


def _run(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        cwd=str(home),
        capture_output=True,
        text=True,
    )


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_help_exits_zero_and_lists_flags(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _run(["--help"], home)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for flag in SUPPORTED_FLAGS:
        assert flag in combined, f"usage missing {flag}"


def test_help_has_no_side_effects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _run(["--help"], home)

    # No state dir created, nothing written under HOME.
    assert not (home / ".fleetent").exists()
    assert list(home.iterdir()) == []


def test_unknown_flag_fails_fast(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _run(["--definitely-not-a-flag"], home)

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "usage" in combined.lower() or "Usage" in combined
