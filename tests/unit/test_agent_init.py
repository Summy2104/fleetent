"""Unit tests for `fleetent agent init` home scaffolding (agent-init-cli)."""

import pytest

from fleetent import agent_config
from fleetent.runtime import agent_init


def test_scaffold_creates_runnable_home(tmp_path) -> None:
    home = tmp_path / "my-bot"
    returned = agent_init.scaffold_agent_home("my-bot", home=home)

    assert returned == home
    assert (home / "agent.yaml").is_file()
    # Runtime loader (agent run) requires dir-name == name; this must pass.
    agent = agent_config.load_agent_file(home)
    assert agent.name == "my-bot"


def test_scaffold_env_lists_referenced_names_without_secrets(tmp_path) -> None:
    home = tmp_path / "my-bot"
    agent_init.scaffold_agent_home("my-bot", home=home)

    env = (home / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_MODEL_PRIMARY_API_KEY=" in env
    assert "ANTHROPIC_API_KEY=" not in env
    assert "model_overrides" not in (home / "agent.yaml").read_text(encoding="utf-8")
    # Scaffold lists names with empty values — never real secret material,
    # except FLEETENT_TUI_TOKEN which is auto-generated with a ma- prefix.
    for marker in ("sk-", "xoxb-", "xapp-"):
        assert marker not in env


def test_scaffold_generates_tui_token_in_env(tmp_path) -> None:
    home = tmp_path / "my-bot"
    agent_init.scaffold_agent_home("my-bot", home=home)

    env = (home / ".env").read_text(encoding="utf-8")
    lines = dict(line.split("=", 1) for line in env.strip().splitlines() if "=" in line)
    assert "FLEETENT_TUI_TOKEN" in lines
    token = lines["FLEETENT_TUI_TOKEN"]
    assert token.startswith("ma-")
    assert len(token) == 67  # "ma-" + 64 hex chars


def test_scaffold_tui_token_unique_per_init(tmp_path) -> None:
    home_a = tmp_path / "bot-a"
    home_b = tmp_path / "bot-b"
    agent_init.scaffold_agent_home("bot-a", home=home_a)
    agent_init.scaffold_agent_home("bot-b", home=home_b)

    def token(home):  # type: ignore[no-untyped-def]
        lines = dict(
            line.split("=", 1)
            for line in (home / ".env").read_text(encoding="utf-8").strip().splitlines()
            if "=" in line
        )
        return lines["FLEETENT_TUI_TOKEN"]

    assert token(home_a) != token(home_b)


def test_scaffold_no_platform_or_db_import() -> None:
    # Pure local scaffold: the module must not depend on platform or the DB runtime.
    from pathlib import Path

    src = Path(agent_init.__file__).read_text(encoding="utf-8")
    assert "fleetent.platform" not in src
    assert "from fleetent.db" not in src and "import fleetent.db" not in src


def test_refuses_overwrite_without_force(tmp_path) -> None:
    home = tmp_path / "my-bot"
    agent_init.scaffold_agent_home("my-bot", home=home)
    (home / "agent.yaml").write_text("name: my-bot\nversion: 99\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        agent_init.scaffold_agent_home("my-bot", home=home)

    assert "version: 99" in (home / "agent.yaml").read_text(encoding="utf-8")


def test_force_overwrites_agent_yaml_but_preserves_env_with_token(tmp_path) -> None:
    home = tmp_path / "my-bot"
    agent_init.scaffold_agent_home("my-bot", home=home)
    (home / "agent.yaml").write_text("name: my-bot\nversion: 99\n", encoding="utf-8")
    existing_token = "ma-" + "c" * 64
    (home / ".env").write_text(
        f"FLEETENT_TUI_TOKEN={existing_token}\n",
        encoding="utf-8",
    )

    agent_init.scaffold_agent_home("my-bot", home=home, force=True)

    assert "version: 99" not in (home / "agent.yaml").read_text(encoding="utf-8")
    assert agent_config.load_agent_file(home).name == "my-bot"
    # .env with a valid token is preserved — token is not rotated.
    env = (home / ".env").read_text(encoding="utf-8")
    assert f"FLEETENT_TUI_TOKEN={existing_token}" in env


def test_scaffold_backfills_token_when_env_exists_without_token(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()
    (home / ".env").write_text("SOME_VAR=value\n", encoding="utf-8")
    agent_init.scaffold_agent_home("my-bot", home=home)

    env = (home / ".env").read_text(encoding="utf-8")
    lines = dict(line.split("=", 1) for line in env.strip().splitlines() if "=" in line)
    assert "FLEETENT_TUI_TOKEN" in lines
    assert lines["FLEETENT_TUI_TOKEN"].startswith("ma-")


def test_default_home_is_under_fleetent_home_default_tenant_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    returned = agent_init.scaffold_agent_home("my-bot")
    assert returned == tmp_path / "tenants" / "default" / "agents" / "my-bot"
    assert (tmp_path / "tenants" / "default" / "agents" / "my-bot" / "agent.yaml").is_file()


# --- ensure_env_scaffold tests (tasks 1.1-1.3) ---


def test_ensure_env_scaffold_creates_env_with_tui_token(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()

    agent_init.ensure_env_scaffold(home)

    env_path = home / ".env"
    assert env_path.exists()
    lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert "FLEETENT_TUI_TOKEN" in lines
    token = lines["FLEETENT_TUI_TOKEN"]
    assert token.startswith("ma-")
    assert len(token) == 67  # "ma-" + 64 hex chars


def test_ensure_env_scaffold_preserves_existing_token(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()
    existing_token = "ma-" + "b" * 64
    (home / ".env").write_text(f"FLEETENT_TUI_TOKEN={existing_token}\n", encoding="utf-8")

    agent_init.ensure_env_scaffold(home)

    lines = dict(
        line.split("=", 1)
        for line in (home / ".env").read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert lines["FLEETENT_TUI_TOKEN"] == existing_token


def test_ensure_env_scaffold_with_referenced_env_names(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()

    agent_init.ensure_env_scaffold(home, referenced_env_names=["ANTHROPIC_API_KEY", "SLACK_TOKEN"])

    content = (home / ".env").read_text(encoding="utf-8")
    lines = dict(line.split("=", 1) for line in content.strip().splitlines() if "=" in line)
    assert lines.get("ANTHROPIC_API_KEY") == ""
    assert lines.get("SLACK_TOKEN") == ""
    assert "FLEETENT_TUI_TOKEN" in lines
    for marker in ("sk-", "xoxb-", "xapp-"):
        assert marker not in content


# --- ensure_env_scaffold with secrets (tasks 2.1–2.2, D1/D3) ---


def test_ensure_env_scaffold_writes_real_value_for_known_secret(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()

    agent_init.ensure_env_scaffold(
        home,
        referenced_env_names=["MODEL_API_KEY", "SLACK_TOKEN"],
        secrets={"MODEL_API_KEY": "sk-live-secret"},
    )

    env_path = home / ".env"
    assert env_path.exists()
    # file must be 0600
    assert oct(env_path.stat().st_mode & 0o777) == oct(0o600)
    lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert lines["MODEL_API_KEY"] == "sk-live-secret"
    assert lines["SLACK_TOKEN"] == ""  # not in secrets → empty placeholder
    assert "FLEETENT_TUI_TOKEN" in lines


def test_ensure_env_scaffold_preserves_tui_token_when_rewriting(tmp_path) -> None:
    home = tmp_path / "my-bot"
    home.mkdir()
    existing_token = "ma-" + "e" * 64
    (home / ".env").write_text(f"FLEETENT_TUI_TOKEN={existing_token}\n", encoding="utf-8")

    agent_init.ensure_env_scaffold(
        home,
        referenced_env_names=["MODEL_API_KEY"],
        secrets={"MODEL_API_KEY": "sk-live-secret"},
    )

    lines = dict(
        line.split("=", 1)
        for line in (home / ".env").read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert lines["FLEETENT_TUI_TOKEN"] == existing_token
    assert lines["MODEL_API_KEY"] == "sk-live-secret"
