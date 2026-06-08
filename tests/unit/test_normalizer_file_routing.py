"""get_agent_for_context resolves from the file index (zero DB) — file-driven-agent-config."""

import yaml

from fleetent import agent_config, agent_store
from fleetent.im_gateway import normalizer


def _write(root, name, **fields):
    doc = {"name": name, "version": 1, "models": agent_config.default_models().model_dump()}
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _explode(*a, **k):
    raise AssertionError("runtime routing must not touch the database")


def test_get_agent_for_context_returns_default_agent(tmp_path, monkeypatch):
    # Channel/user routing removed; only default agent is returned.
    _write(tmp_path, "def", system_prompt="D")
    agent_config.scan(tmp_path)
    # All single-agent indexes are forced-default; but scan() does not force default
    # in multi-scan mode. Use a single-agent index here.
    agent_config._index = agent_config.AgentConfigIndex(
        agents={"def": agent_config._index.get("def")},
        default="def",
    )
    agent = normalizer.get_agent_for_context("slack", "C1", "u1")
    assert agent is not None and agent.name == "def"
    assert agent.system_prompt == "D"


def test_get_agent_for_context_none_when_no_default(tmp_path, monkeypatch):
    # Without a default agent, returns None regardless of channel/user.
    _write(tmp_path, "lonely", system_prompt="P")
    agent_config.scan(tmp_path)
    # scan sets default=None for multi-agent scans
    assert normalizer.get_agent_for_context("slack", "C-none", "u-none") is None


def test_get_agent_for_context_does_not_touch_db(tmp_path, monkeypatch):
    _write(tmp_path, "solo", system_prompt="S")
    agent_config.scan(tmp_path)
    monkeypatch.setattr(agent_store, "get_agent_for_channel", _explode)
    monkeypatch.setattr(agent_store, "get_agent_for_user", _explode)
    monkeypatch.setattr(agent_store, "get_default_agent", _explode)
    # Does not raise despite db being wired to explode
    normalizer.get_agent_for_context("slack", "C1", "u1")
