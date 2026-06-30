from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fleetent.platform.platform_cli.main import main as platform_cli_main

_REPO_ROOT = Path(__file__).resolve().parents[2]


def run_platform(*args: str) -> tuple[str, str, int]:
    """Run platform CLI with given CLI args. Returns (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            platform_cli_main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def _canonical_platform_env() -> str:
    return (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")


def _canonical_platform_yaml() -> str:
    return (_REPO_ROOT / "platform.yaml.example").read_text(encoding="utf-8")


def test_init_config_dry_run_prints_planned_paths_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out, err, code = run_platform("init-config", "--dry-run", "--home", str(tmp_path))

    assert code == 0
    assert err == ""
    for path in [
        ".env",
        "platform.yaml",
        "logs/",
        "diagnostics/",
        "secrets/",
    ]:
        assert f"create {path}" in out
    assert "config/settings.yaml" not in out
    assert "config/mcp.servers.yaml" not in out

    for path in [".env", "platform.yaml", "logs", "diagnostics", "secrets"]:
        assert not (tmp_path / path).exists()


def test_init_config_skips_existing_files_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existing_env = tmp_path / ".env"
    existing_env.write_text("OPENAI_API_KEY=local\n", encoding="utf-8")

    out, err, code = run_platform("init-config", "--home", str(tmp_path))

    assert code == 0
    assert err == ""
    assert "skip .env" in out
    assert "create platform.yaml" in out
    assert "config/settings.yaml" not in out
    assert existing_env.read_text(encoding="utf-8") == "OPENAI_API_KEY=local\n"
    assert (tmp_path / "platform.yaml").read_text(encoding="utf-8") == _canonical_platform_yaml()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "diagnostics").is_dir()
    assert not (tmp_path / "data").exists()
    assert (tmp_path / "secrets").is_dir()


def test_init_config_force_overwrites_generated_files_and_keeps_unknown_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=local\n", encoding="utf-8")
    unknown_secret = tmp_path / "secrets" / "operator-note"
    unknown_secret.parent.mkdir()
    unknown_secret.write_text("keep me\n", encoding="utf-8")

    out, err, code = run_platform("init-config", "--force", "--home", str(tmp_path))

    assert code == 0
    assert err == ""
    assert "overwrite .env" in out
    assert "create platform.yaml" in out
    assert (tmp_path / ".env").read_text(encoding="utf-8") == _canonical_platform_env()
    assert unknown_secret.read_text(encoding="utf-8") == "keep me\n"


def test_init_config_uses_explicit_home_instead_of_cwd(tmp_path, monkeypatch):
    template_root = tmp_path / "outside-repo"
    template_root.mkdir()
    target_root = tmp_path / "home"
    monkeypatch.chdir(template_root)

    out, err, code = run_platform("init-config", "--home", str(target_root))

    assert code == 0
    assert err == ""
    assert "create .env" in out
    assert (target_root / ".env").read_text(encoding="utf-8") == _canonical_platform_env()
    assert (target_root / "platform.yaml").read_text(encoding="utf-8") == _canonical_platform_yaml()
    assert not (template_root / ".env").exists()
    assert not (template_root / "platform.yaml").exists()


def test_init_config_defaults_to_fleetent_home_instead_of_cwd(tmp_path, monkeypatch):
    template_root = tmp_path / "outside-repo"
    template_root.mkdir()
    target_root = tmp_path / "fleetent-home"
    monkeypatch.chdir(template_root)
    monkeypatch.setenv("FLEETENT_HOME", str(target_root))

    out, err, code = run_platform("init-config")

    assert code == 0
    assert err == ""
    assert "create .env" in out
    assert (target_root / ".env").read_text(encoding="utf-8") == _canonical_platform_env()
    assert (target_root / "platform.yaml").read_text(encoding="utf-8") == _canonical_platform_yaml()
    assert not (template_root / ".env").exists()
    assert not (template_root / "platform.yaml").exists()
