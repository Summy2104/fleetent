from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from fleetent import __main__ as cli


def _run_cli(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            cli.main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_kb_service_init_config_defaults_to_default_tenant_home_outside_repo_cwd(
    monkeypatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    outside_repo = tmp_path / "outside-repo"
    outside_repo.mkdir()
    monkeypatch.chdir(outside_repo)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb", "init-config")

    assert code == 0
    assert err == ""
    assert "create tenants/default/kb/kb-service.yaml" in out
    assert "create tenants/default/kb/.env" in out
    assert "next: review tenants/default/kb/kb-service.yaml and tenants/default/kb/.env" in out
    config_path = home_dir / "tenants" / "default" / "kb" / "kb-service.yaml"
    env_path = home_dir / "tenants" / "default" / "kb" / ".env"
    assert config_path.exists()
    assert env_path.exists()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["service"]["tenant_id"] == "default"
    assert config["data"]["home"] == "./data"


def test_kb_service_init_config_creates_requested_tenant_home(monkeypatch, tmp_path: Path) -> None:
    home_dir = tmp_path / "home"
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb", "init-config", "--tenant", "acme")

    assert code == 0
    assert err == ""
    assert "create tenants/acme/kb/kb-service.yaml" in out
    assert "create tenants/acme/kb/.env" in out
    assert "next: review tenants/acme/kb/kb-service.yaml and tenants/acme/kb/.env" in out
    config_path = home_dir / "tenants" / "acme" / "kb" / "kb-service.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["service"]["tenant_id"] == "acme"
    assert [connector["enabled"] for connector in config["connectors"]] == [False, False]


def test_kb_service_init_config_skips_existing_and_force_overwrites_within_tenant_home(
    monkeypatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    service_dir = home_dir / "tenants" / "tenant-a" / "kb"
    service_dir.mkdir(parents=True)
    yaml_path = service_dir / "kb-service.yaml"
    env_path = service_dir / ".env"
    yaml_path.write_text("tenant: existing\n", encoding="utf-8")
    env_path.write_text("KB_SERVICE_KEY=existing\n", encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb", "init-config", "--tenant", "tenant-a")

    assert code == 0
    assert err == ""
    assert "skip tenants/tenant-a/kb/kb-service.yaml" in out
    assert "skip tenants/tenant-a/kb/.env" in out
    assert yaml_path.read_text(encoding="utf-8") == "tenant: existing\n"
    assert env_path.read_text(encoding="utf-8") == "KB_SERVICE_KEY=existing\n"

    out, err, code = _run_cli("kb", "init-config", "--tenant", "tenant-a", "--force")

    assert code == 0
    assert err == ""
    assert "overwrite tenants/tenant-a/kb/kb-service.yaml" in out
    assert "overwrite tenants/tenant-a/kb/.env" in out
    assert yaml_path.read_text(encoding="utf-8") != "tenant: existing\n"
    assert env_path.read_text(encoding="utf-8") != "KB_SERVICE_KEY=existing\n"
