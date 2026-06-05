from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fleetent.platform.admin_cli.main import main as admin_cli_main


def run_admin(*args: str) -> tuple[str, str, int]:
    """Run admin CLI with given CLI args. Returns (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent-admin", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin_cli_main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def write_config_examples(root: Path) -> None:
    # init-config seeds .env from the platform template under config/platform/.
    platform_dir = root / "config" / "platform"
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / ".env.example").write_text("FLEETENT_AUTO_UPGRADE=false\n", encoding="utf-8")


def test_init_config_dry_run_prints_planned_paths_without_writing(tmp_path, monkeypatch):
    write_config_examples(tmp_path)
    monkeypatch.chdir(tmp_path)

    out, err, code = run_admin("init-config", "--dry-run")

    assert code == 0
    assert err == ""
    for path in [
        ".env",
        "data/",
        "data/logs/",
        "data/diagnostics/",
        "secrets/",
    ]:
        assert f"create {path}" in out
    assert "config/settings.yaml" not in out
    assert "config/mcp.servers.yaml" not in out

    for path in [".env", "data", "secrets"]:
        assert not (tmp_path / path).exists()


def test_init_config_skips_existing_files_by_default(tmp_path, monkeypatch):
    write_config_examples(tmp_path)
    monkeypatch.chdir(tmp_path)
    existing_env = tmp_path / ".env"
    existing_env.write_text("OPENAI_API_KEY=local\n", encoding="utf-8")

    out, err, code = run_admin("init-config")

    assert code == 0
    assert err == ""
    assert "skip .env" in out
    assert "config/settings.yaml" not in out
    assert existing_env.read_text(encoding="utf-8") == "OPENAI_API_KEY=local\n"
    assert (tmp_path / "data/logs").is_dir()
    assert (tmp_path / "data/diagnostics").is_dir()
    assert (tmp_path / "secrets").is_dir()


def test_init_config_force_overwrites_generated_files_and_keeps_unknown_files(
    tmp_path, monkeypatch
):
    write_config_examples(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=local\n", encoding="utf-8")
    unknown_secret = tmp_path / "secrets" / "operator-note"
    unknown_secret.parent.mkdir()
    unknown_secret.write_text("keep me\n", encoding="utf-8")

    out, err, code = run_admin("init-config", "--force")

    assert code == 0
    assert err == ""
    assert "overwrite .env" in out
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "FLEETENT_AUTO_UPGRADE=false\n"
    assert unknown_secret.read_text(encoding="utf-8") == "keep me\n"
