"""Behavioral tests for scripts/install-agent.sh (agent-host installer).

install-agent.sh installs the fleetent runtime + node supervisor, sets FLEETENT_HOME,
and prints a tutorial guiding the operator to configure `$FLEETENT_HOME/node/.env`
and start `fleetent node start`. It does not scaffold an agent home, and mentions
`fleetent agent init` / `fleetent agent run` only as dev/test workflows.

All runs are isolated to a temp HOME via a fake `uv` on PATH that stubs `tool install`
(seeding no-op entrypoints) and `python`, so nothing touches the network or the real
environment.
"""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install-agent.sh"
_RETIRED_TUI_CMD = "fleetent" + "-tui"

_FAKE_UV = """#!/bin/bash
echo "uv $*" >> "$UV_LOG"
case "$1" in
  --version) echo "uv 0.5.0 (fake)" ;;
  python) [ "${FAKE_PYTHON_OK:-1}" = "1" ] && exit 0 || exit 1 ;;
  tool)
    if [ "$2" = "install" ]; then
      printf '#!/bin/bash\\n:' > "$FAKE_BIN/fleetent"; chmod +x "$FAKE_BIN/fleetent"
    fi
    ;;
esac
exit 0
"""


def _env(home: Path, fake_bin: Path, uv_log: Path, **flags: str) -> dict[str, str]:
    fake_bin.mkdir(parents=True, exist_ok=True)
    uv = fake_bin / "uv"
    uv.write_text(_FAKE_UV)
    uv.chmod(0o755)
    env = {
        "HOME": str(home),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "UV_LOG": str(uv_log),
        "FAKE_BIN": str(fake_bin),
        "SHELL": "/bin/bash",
    }
    env.update(flags)
    return env


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, cwd=str(cwd), capture_output=True, text=True
    )


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_install_without_agent_id_installs_runtime_and_prints_tutorial(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _env(home, tmp_path / "bin", uv_log)

    result = _run([], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    # Runtime installed; no agent init was run.
    assert "tool install" in uv_log.read_text()
    assert "agent init" not in uv_log.read_text()
    # Tutorial guides the operator to configure node and start it against platform.
    assert "node supervisor" in out
    assert "$FLEETENT_HOME/node/.env" in out
    assert "fleetent node start" in out
    assert "FLEETENT_NODE_PLATFORM_URL" in out
    assert "FLEETENT_NODE_ID" in out
    assert "FLEETENT_NODE_SERVICE_KEY" in out
    # agent init/run remain available only as dev/test guidance.
    assert "dev/test" in out
    assert "fleetent agent init" in out
    assert "fleetent agent run" in out
    assert _RETIRED_TUI_CMD not in out
    # No agent home produced by the script.
    assert not (home / ".fleetent" / "agents").exists()


def test_positional_agent_id_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run(["some-id"], env, home)

    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined
    assert "agent init" in combined  # points the operator at the real create command


def test_no_alembic_invoked(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uv_log = tmp_path / "uv.log"
    env = _env(home, tmp_path / "bin", uv_log)

    _run([], env, home)

    assert "alembic" not in uv_log.read_text()


def test_dir_flag_overrides_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom"
    env = _env(home, tmp_path / "bin", tmp_path / "uv.log")

    result = _run(["--dir", str(custom)], env, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(custom) in (result.stdout + result.stderr)


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = _env(home, tmp_path / "bin", tmp_path / "uv.log")

    r1 = _run([], env, home)
    r2 = _run([], env, home)

    assert r1.returncode == 0 and r2.returncode == 0
