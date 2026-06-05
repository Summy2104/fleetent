"""Platform materializes a runnable agent home (agent.yaml + .env scaffold)."""


from fleetent.agent_config import (
    AgentAccess,
    AgentConnectors,
    AgentFile,
    SlackConnector,
    load_agent_file,
)
from fleetent.platform.agent_lifecycle import materialize


def _agent(name="support", **fields):
    base = dict(
        name=name,
        version=1,
        system_prompt="Help the user.",
        allowed_tools=["shell"],
        allowed_skills=["weather"],
        access=AgentAccess(allow_users=["u_alice"]),
        connectors=AgentConnectors(
            slack=SlackConnector(bot_token_env="SUP_BOT", app_token_env="SUP_APP")
        ),
    )
    base.update(fields)
    return AgentFile(**base)


def test_create_writes_runnable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())

    assert home == tmp_path / "support"
    af = load_agent_file(home)  # round-trips through the home schema (dir name == name)
    assert af.system_prompt == "Help the user."
    assert af.allowed_tools == ["shell"]
    assert af.access.allow_users == ["u_alice"]
    assert af.connectors.slack is not None
    assert af.connectors.slack.bot_token_env == "SUP_BOT"


def test_env_scaffold_has_names_only_no_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "SUP_BOT=" in env_text
    assert "SUP_APP=" in env_text
    # only names, no secret values seeded
    for line in env_text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            assert line.split("=", 1)[1] == ""


def test_update_rewrites_yaml_preserves_env_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())
    # operator fills in a real secret
    (home / ".env").write_text("SUP_BOT=xoxb-real\nSUP_APP=xapp-real\n", encoding="utf-8")

    # edit the definition and re-materialize
    materialize.write_home(_agent(system_prompt="Updated prompt."))

    af = load_agent_file(home)
    assert af.system_prompt == "Updated prompt."  # yaml rewritten
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "SUP_BOT=xoxb-real" in env_text  # operator value preserved
    assert "SUP_APP=xapp-real" in env_text


def test_default_closed_access_when_not_authored(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = AgentFile(name="bare", version=1)  # no access block authored
    home = materialize.write_home(agent)
    af = load_agent_file(home)
    assert af.access.require_approval is True
    assert af.access.allow_users == []
