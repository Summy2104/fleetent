from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _fake_fleetent(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "fleetent"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$FLEETENT_ENTRYPOINT_LOG\"\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run_entrypoint(tmp_path: Path, *args: str, auto_upgrade: bool = False) -> subprocess.CompletedProcess[str]:
    log_path = tmp_path / "entrypoint.log"
    env = os.environ.copy()
    env["PATH"] = f"{_fake_fleetent(tmp_path)}:{env['PATH']}"
    env["FLEETENT_ENTRYPOINT_LOG"] = str(log_path)
    if auto_upgrade:
        env["FLEETENT_AUTO_UPGRADE"] = "true"
    return subprocess.run(
        ["bash", "scripts/docker_entrypoint.sh", *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _commands(tmp_path: Path) -> list[str]:
    log_path = tmp_path / "entrypoint.log"
    if not log_path.exists():
        return []
    return log_path.read_text(encoding="utf-8").splitlines()


def test_entrypoint_defaults_to_platform_role(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path)

    assert result.returncode == 0
    assert _commands(tmp_path) == ["platform serve --host 0.0.0.0 --port 8765"]


def test_entrypoint_dispatches_supported_roles(tmp_path: Path) -> None:
    expected = {
        "platform": "platform serve --host 0.0.0.0 --port 8765",
        "node": "node start",
        "kb-worker": "kb-worker",
        "agent": "agent run support",
    }

    for role, command in expected.items():
        role_tmp = tmp_path / role
        role_tmp.mkdir()
        args = (role, "support") if role == "agent" else (role,)
        result = _run_entrypoint(role_tmp, *args)

        assert result.returncode == 0
        assert _commands(role_tmp) == [command]


def test_entrypoint_allows_explicit_fleetent_cli(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, "fleetent", "version")

    assert result.returncode == 0
    assert _commands(tmp_path) == ["version"]


def test_entrypoint_rejects_unknown_role(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, "unknown")

    assert result.returncode != 0
    assert "unsupported role" in result.stderr
    assert _commands(tmp_path) == []


def test_entrypoint_auto_upgrade_only_runs_for_platform(tmp_path: Path) -> None:
    platform = tmp_path / "platform"
    platform.mkdir()
    node = tmp_path / "node"
    node.mkdir()

    platform_result = _run_entrypoint(platform, "platform", auto_upgrade=True)
    node_result = _run_entrypoint(node, "node", auto_upgrade=True)

    assert platform_result.returncode == 0
    assert _commands(platform) == [
        "platform upgrade",
        "platform serve --host 0.0.0.0 --port 8765",
    ]
    assert node_result.returncode == 0
    assert _commands(node) == ["node start"]
