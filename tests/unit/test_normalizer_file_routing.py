"""get_agent_for_context resolves from the file index (zero DB) — file-driven-agent-config."""

import yaml

from fleetent import agent_config, agent_store
from fleetent.im_gateway import normalizer


def _write(root, name, **fields):
    doc = {"name": name, "version": 1}
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _explode(*a, **k):
    raise AssertionError("runtime routing must not touch the database")


def test_get_agent_for_context_channel_beats_user_and_default(tmp_path, monkeypatch):
    _write(tmp_path, "chan", system_prompt="C", bindings={"channels": ["slack:C1"]})
    _write(tmp_path, "usr", system_prompt="U", bindings={"users": ["u1"]})
    _write(tmp_path, "def", system_prompt="D", bindings={"default": True})
    agent_config.scan(tmp_path)
    agent = normalizer.get_agent_for_context("slack", "C1", "u1")
    assert agent is not None and agent.name == "chan"
    assert agent.system_prompt == "C"


def test_get_agent_for_context_user_fallback(tmp_path, monkeypatch):
    _write(tmp_path, "usr", system_prompt="U", bindings={"users": ["u1"]})
    _write(tmp_path, "def", system_prompt="D", bindings={"default": True})
    agent_config.scan(tmp_path)
    agent = normalizer.get_agent_for_context("slack", "C-none", "u1")
    assert agent is not None and agent.name == "usr"


def test_get_agent_for_context_default_fallback(tmp_path, monkeypatch):
    _write(tmp_path, "def", system_prompt="D", bindings={"default": True})
    agent_config.scan(tmp_path)
    agent = normalizer.get_agent_for_context("slack", "C-none", "u-none")
    assert agent is not None and agent.name == "def"


def test_get_agent_for_context_none_when_unbound(tmp_path, monkeypatch):
    _write(tmp_path, "lonely", system_prompt="P")  # no bindings, no default
    agent_config.scan(tmp_path)
    assert normalizer.get_agent_for_context("slack", "C-none", "u-none") is None


def test_get_agent_for_context_does_not_touch_db(tmp_path, monkeypatch):
    _write(tmp_path, "chan", system_prompt="C", bindings={"channels": ["slack:C1"]})
    agent_config.scan(tmp_path)
    monkeypatch.setattr(agent_store, "get_agent_for_channel", _explode)
    monkeypatch.setattr(agent_store, "get_agent_for_user", _explode)
    monkeypatch.setattr(agent_store, "get_default_agent", _explode)
    agent = normalizer.get_agent_for_context("slack", "C1", "u1")
    assert agent is not None and agent.name == "chan"
