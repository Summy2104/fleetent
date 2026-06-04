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


# ── fake-uv harness ─────────────────────────────────────────────────────────
# A stub `uv` on PATH lets us exercise ensure_uv/check_python/install_tool
# without touching the network. It logs every invocation and, on `tool install`,
# can create the three entrypoints so install_tool's verification passes.

_FAKE_UV = """#!/bin/bash
echo "uv $*" >> "$UV_LOG"
case "$1" in
  --version) echo "uv 0.5.0 (fake)" ;;
  python)
    [ "${FAKE_PYTHON_OK:-1}" = "1" ] && exit 0 || exit 1
    ;;
  tool)
    if [ "$2" = "install" ] && [ "${FAKE_TOOL_CREATES_ENTRYPOINTS:-1}" = "1" ]; then
      for c in fleetent fleetent-admin fleetent-tui; do
        printf '#!/bin/bash\\n:' > "$FAKE_BIN/$c"; chmod +x "$FAKE_BIN/$c"
      done
    fi
    ;;
esac
exit 0
"""


def _fake_uv_env(home: Path, fake_bin: Path, uv_log: Path, **flags: str) -> dict[str, str]:
    fake_bin.mkdir(parents=True, exist_ok=True)
    uv = fake_bin / "uv"
    uv.write_text(_FAKE_UV)
    uv.chmod(0o755)
    # Minimal PATH: fake uv + system essentials only. Excludes ~/.local/bin so a
    # real installed `fleetent` can't leak into command -v checks.
    env = {
        "HOME": str(home),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "UV_LOG": str(uv_log),
        "FAKE_BIN": str(fake_bin),
        "SHELL": "/bin/bash",  # deterministic rc target (~/.bashrc)
    }
    env.update(flags)
    return env


def _run_env(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def test_install_tool_invokes_uv_tool_install(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _fake_uv_env(home, tmp_path / "bin", uv_log)

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tool install" in uv_log.read_text()


def test_existing_uv_is_reused_not_installed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    # uv present on PATH → no self-install attempt.
    assert "Installing uv" not in (result.stdout + result.stderr)


def test_check_python_fails_fast_when_no_312(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log", FAKE_PYTHON_OK="0")

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    assert result.returncode != 0
    assert "3.12" in (result.stdout + result.stderr)


def test_missing_entrypoint_reports_recovery_hint(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(
        home, tmp_path / "bin", tmp_path / "uv.log", FAKE_TOOL_CREATES_ENTRYPOINTS="0"
    )

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "uv tool install" in combined


def test_default_fleetent_home_created_and_persisted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".fleetent").is_dir()
    rc = (home / ".bashrc").read_text()
    assert f'export FLEETENT_HOME="{home / ".fleetent"}"' in rc


def test_fleetent_home_persist_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    _run_env(["--skip-db", "--skip-config"], env, home)
    _run_env(["--skip-db", "--skip-config"], env, home)

    rc = (home / ".bashrc").read_text()
    assert rc.count("export FLEETENT_HOME=") == 1


def test_dir_flag_overrides_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom-home"
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env(["--dir", str(custom), "--skip-db", "--skip-config"], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert custom.is_dir()
    assert f'export FLEETENT_HOME="{custom}"' in (home / ".bashrc").read_text()


def test_path_hint_when_local_bin_absent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")  # PATH lacks ~/.local/bin

    result = _run_env(["--skip-db", "--skip-config"], env, home)

    assert ".local/bin" in (result.stdout + result.stderr)
