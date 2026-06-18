"""Behavioral tests for the developer installer scripts/install.sh.

install-script-split: install.sh is now a thin developer orchestrator — editable
`uv tool install`, then delegation to the role scripts (install-platform.sh /
install-agent.sh) plus its own Alembic db init. The old monolithic flags
(--skip-db/--skip-config), shell-rc persistence, docker probe and PATH hints
moved out with the split, so they are no longer asserted here.

All runs are isolated to a temp HOME/CWD; network-touching steps run through a
fake `uv` on PATH that logs invocations and seeds the expected entrypoints.
"""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install.sh"
SUPPORTED_FLAGS = ("--agent-only", "--platform-only", "--dir", "--help")


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
    # The dev installer points production installs at the role scripts.
    assert "install-agent.sh" in combined
    assert "install-platform.sh" in combined


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
# A stub `uv` on PATH lets us exercise ensure_uv/check_python/install_editable
# and the delegated role scripts without touching the network. It logs every
# invocation and, on `tool install`, creates the three entrypoints so the role
# scripts' `command -v fleetent` checks pass.

_FAKE_UV = """#!/bin/bash
echo "uv $*" >> "$UV_LOG"
# Dump the contents of any -c <file> arg (alembic config) so tests can inspect it.
prev=""
for a in "$@"; do
  if [ "$prev" = "-c" ] && [ -f "$a" ]; then cat "$a" >> "$UV_LOG"; fi
  prev="$a"
done
case "$1" in
  --version) echo "uv 0.5.0 (fake)" ;;
  python)
    [ "${FAKE_PYTHON_OK:-1}" = "1" ] && exit 0 || exit 1
    ;;
  tool)
    if [ "$2" = "install" ]; then
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
        "SHELL": "/bin/bash",
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


def test_installs_editable_tool(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _fake_uv_env(home, tmp_path / "bin", uv_log)

    result = _run_env([], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    # Developer mode keeps the source tree as the live import path.
    assert "tool install --force --editable" in uv_log.read_text()


def test_existing_uv_is_reused_not_installed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env([], env, home)

    # uv present on PATH → no self-install attempt.
    assert "Installing uv" not in (result.stdout + result.stderr)


def test_check_python_fails_fast_when_no_312(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log", FAKE_PYTHON_OK="0")

    result = _run_env([], env, home)

    assert result.returncode != 0
    assert "3.12" in (result.stdout + result.stderr)


def test_full_run_delegates_to_both_role_scripts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env([], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    assert "Setting up platform" in out
    # install-defer-agent-init: no default agent is seeded; a create-agent tutorial is printed.
    assert "fleetent agent init" in out
    assert not (home / ".fleetent" / "agents" / "default").exists()
    assert "Developer install complete" in out


def test_init_db_runs_alembic_against_fleetent_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _fake_uv_env(home, tmp_path / "bin", uv_log)

    result = _run_env([], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    log = uv_log.read_text()
    assert "alembic" in log and "upgrade head" in log
    # The transient alembic config targets the FLEETENT_HOME database.
    assert f"sqlite:///{home / '.fleetent' / 'data' / 'management.db'}" in log
    assert (home / ".fleetent" / "data").is_dir()


def test_dir_flag_overrides_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom-home"
    uv_log = tmp_path / "uv.log"
    env = _fake_uv_env(home, tmp_path / "bin", uv_log)

    result = _run_env(["--dir", str(custom)], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"sqlite:///{custom / 'data' / 'management.db'}" in uv_log.read_text()
    assert (custom / "data").is_dir()
    assert not (home / ".fleetent" / "data").exists()


def test_agent_only_skips_platform_and_db(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _fake_uv_env(home, tmp_path / "bin", uv_log)

    result = _run_env(["--agent-only"], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    # Agent component now only installs the runtime + prints the create-agent tutorial.
    assert "fleetent agent init" in out
    assert "Setting up platform" not in out
    assert "upgrade head" not in uv_log.read_text()
    assert not (home / ".fleetent" / "agents" / "default").exists()


def test_platform_only_skips_agent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run_env(["--platform-only"], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    assert "Setting up platform" in out
    # platform-only skips the agent component entirely → no create-agent tutorial.
    assert "fleetent agent init" not in out


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _fake_uv_env(home, tmp_path / "bin", tmp_path / "uv.log")

    r1 = _run_env([], env, home)
    r2 = _run_env([], env, home)

    assert r1.returncode == 0 and r2.returncode == 0
