"""Single-file agent home flows through scan()/current() into runtime resolution."""

import yaml

from fleetent import agent_config
from fleetent.runtime import snapshot


def _write_home_agent(home, **overrides) -> None:
    doc = {
        "name": "default",
        "version": 1,
        "system_prompt": "You are deployed.",
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    doc.update(overrides)
    agent_home = home / "tenants" / "default" / "agents" / "default"
    agent_home.mkdir(parents=True, exist_ok=True)
    (agent_home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_scan_publishes_single_home_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_home_agent(tmp_path)

    agent_config.scan()
    index = agent_config.current()

    assert set(index.agents) == {"default"}
    assert index.default == "default"


def test_request_resolves_to_home_agent_via_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_home_agent(tmp_path)
    agent_config.scan()

    # No channel/user match -> falls back to the forced-default home agent.
    snap = snapshot.resolve_agent_for_request(platform=None, channel_id=None, user_id=None)

    assert snap is not None
    assert snap.name == "default"
    assert snap.system_prompt == "You are deployed."


def test_home_agent_resolves_regardless_of_channel(tmp_path, monkeypatch) -> None:
    # bindings were removed from AgentFile: the deployed home agent is the forced
    # default, so any channel id resolves to it.
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_home_agent(tmp_path)
    agent_config.scan()

    snap = snapshot.resolve_agent_for_request(platform="slack", channel_id="C9", user_id=None)

    assert snap is not None and snap.name == "default"
