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
    # Scaffold lists names with empty values — never real secret material.
    for marker in ("sk-", "xoxb-", "xapp-", "ma-"):
        assert marker not in env


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


def test_force_overwrites_agent_yaml_but_preserves_env(tmp_path) -> None:
    home = tmp_path / "my-bot"
    agent_init.scaffold_agent_home("my-bot", home=home)
    (home / "agent.yaml").write_text("name: my-bot\nversion: 99\n", encoding="utf-8")
    (home / ".env").write_text("FLEETENT_MODEL_PRIMARY_API_KEY=sk-real-keepme\n", encoding="utf-8")

    agent_init.scaffold_agent_home("my-bot", home=home, force=True)

    assert "version: 99" not in (home / "agent.yaml").read_text(encoding="utf-8")
    assert agent_config.load_agent_file(home).name == "my-bot"
    # .env is never clobbered, even with --force (protects secrets).
    assert (home / ".env").read_text(
        encoding="utf-8"
    ) == "FLEETENT_MODEL_PRIMARY_API_KEY=sk-real-keepme\n"


def test_default_home_is_fleetent_home_slash_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    returned = agent_init.scaffold_agent_home("my-bot")
    assert returned == tmp_path / "my-bot"
    assert (tmp_path / "my-bot" / "agent.yaml").is_file()
