from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_includes_all_canonical_init_config_templates(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    wheel_path = next(dist_dir.glob("fleetent-*.whl"))
    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    assert "fleetent/platform/resources/.env.example" in names
    assert "fleetent/platform/resources/platform.yaml.example" in names
    assert "fleetent/node/resources/node.env.example" in names
    assert "fleetent/runtime/resources/agent.yaml.example" in names
    assert "fleetent/runtime/resources/agent.env.example" in names
    assert "fleetent/knowledge_base/resources/kb-service.yaml.example" in names
    assert "fleetent/knowledge_base/resources/kb-service.env.example" in names


def _run_cli_outside_repo(
    tmp_path: Path,
    *args: str,
    home_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    outside_repo = tmp_path / "outside-repo"
    outside_repo.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": str(repo_root / "src"),
    }
    if home_dir is not None:
        env["FLEETENT_HOME"] = str(home_dir)
    return subprocess.run(
        [sys.executable, "-m", "fleetent", *args],
        cwd=outside_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_platform_init_config_generates_files_outside_repo_cwd(tmp_path: Path) -> None:
    home_dir = tmp_path / "platform-home"

    result = _run_cli_outside_repo(tmp_path, "platform", "init-config", home_dir=home_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "create .env" in result.stdout
    assert "create platform.yaml" in result.stdout
    assert (home_dir / ".env").exists()
    assert (home_dir / "platform.yaml").exists()
    assert (home_dir / "logs").is_dir()
    assert (home_dir / "diagnostics").is_dir()
    assert (home_dir / "secrets").is_dir()


def test_node_init_config_generates_files_outside_repo_cwd(tmp_path: Path) -> None:
    home_dir = tmp_path / "node-home"

    result = _run_cli_outside_repo(tmp_path, "node", "init-config", home_dir=home_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "create node/.env" in result.stdout
    assert (home_dir / "node" / ".env").exists()


def test_kb_service_init_config_generates_tenant_kb_home_outside_repo_cwd(tmp_path: Path) -> None:
    home_dir = tmp_path / "kb-home"

    result = _run_cli_outside_repo(
        tmp_path,
        "kb-service",
        "init-config",
        "--tenant",
        "acme",
        home_dir=home_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "create tenants/acme/kb/kb-service.yaml" in result.stdout
    assert "create tenants/acme/kb/.env" in result.stdout
    assert (home_dir / "tenants" / "acme" / "kb" / "kb-service.yaml").exists()
    assert (home_dir / "tenants" / "acme" / "kb" / ".env").exists()
