"""CLI dispatch tests for `fleetent agent init` (agent-init-cli)."""

import pytest

from fleetent import __main__ as cli
from fleetent import agent_config


def test_agent_init_dispatch_scaffolds_home(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "init", "my-bot"])

    cli.main()

    home = tmp_path / "my-bot"
    assert (home / "agent.yaml").is_file()
    assert agent_config.load_agent_file(home).name == "my-bot"
    out = capsys.readouterr().out
    assert "agent run my-bot" in out


def test_agent_init_honors_home_and_force(tmp_path, monkeypatch) -> None:
    target = tmp_path / "custom"
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "init", "my-bot", "--home", str(target)])
    cli.main()
    assert (target / "agent.yaml").is_file()

    # Second run without --force exits non-zero (refuses overwrite).
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "init", "my-bot", "--home", str(target)])
    with pytest.raises((SystemExit, FileExistsError)):
        cli.main()


def test_agent_init_missing_id_errors(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "init"])
    with pytest.raises(SystemExit):
        cli.main()
