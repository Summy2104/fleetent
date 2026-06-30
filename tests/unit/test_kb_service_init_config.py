from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

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


def test_kb_service_init_config_creates_home_files_outside_repo_cwd(
    monkeypatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    outside_repo = tmp_path / "outside-repo"
    outside_repo.mkdir()
    monkeypatch.chdir(outside_repo)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb-service", "init-config")

    assert code == 0
    assert err == ""
    assert "create kb-service/kb-service.yaml" in out
    assert "create kb-service/.env" in out
    assert (home_dir / "kb-service" / "kb-service.yaml").exists()
    assert (home_dir / "kb-service" / ".env").exists()


def test_kb_service_init_config_skips_existing_and_force_overwrites(
    monkeypatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    service_dir = home_dir / "kb-service"
    service_dir.mkdir(parents=True)
    yaml_path = service_dir / "kb-service.yaml"
    env_path = service_dir / ".env"
    yaml_path.write_text("tenant: existing\n", encoding="utf-8")
    env_path.write_text("KB_SERVICE_KEY=existing\n", encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb-service", "init-config")

    assert code == 0
    assert err == ""
    assert "skip kb-service/kb-service.yaml" in out
    assert "skip kb-service/.env" in out
    assert yaml_path.read_text(encoding="utf-8") == "tenant: existing\n"
    assert env_path.read_text(encoding="utf-8") == "KB_SERVICE_KEY=existing\n"

    out, err, code = _run_cli("kb-service", "init-config", "--force")

    assert code == 0
    assert err == ""
    assert "overwrite kb-service/kb-service.yaml" in out
    assert "overwrite kb-service/.env" in out
    assert yaml_path.read_text(encoding="utf-8") != "tenant: existing\n"
    assert env_path.read_text(encoding="utf-8") != "KB_SERVICE_KEY=existing\n"
