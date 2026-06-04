"""Standalone agent runtime: boot one agent home, bind IM, optional HTTP — no platform."""

import yaml

from fleetent import agent_config
from fleetent.runtime import agent_app


class _FakeSupervisor:
    def __init__(self):
        self.started: list[str] = []

    async def start(self, agent_name: str) -> None:
        self.started.append(agent_name)

    async def stop_all(self) -> None:
        pass


def _write_home(tmp_path, name="support", **fields):
    home = tmp_path / name
    home.mkdir(parents=True, exist_ok=True)
    doc = {"name": name, "version": 1, "system_prompt": "I am support."}
    doc.update(fields)
    (home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return home


async def test_boot_publishes_single_agent_index(tmp_path, monkeypatch):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    rt = await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)

    index = agent_config.current()
    assert set(index.agents) == {"support"}
    assert index.default == "support"
    assert rt.agent.name == "support"
    assert rt.agent.system_prompt == "I am support."


async def test_boot_starts_agent_slack_connector(tmp_path):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)
    assert sup.started == ["support"]


async def test_boot_skips_im_when_disabled(tmp_path):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False, start_im=False)
    assert sup.started == []


def test_build_app_serves_chat_ws_health_and_no_admin():
    app = agent_app.build_app("support")
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/chat" in paths
    assert "/ws" in paths
    assert "/health" in paths
    # No platform admin surface on the agent runtime.
    assert not any(p and p.startswith("/admin") for p in paths)


def test_resolve_home_uses_fleetent_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert agent_app.resolve_home("support") == tmp_path / "support"
    # explicit override wins
    assert agent_app.resolve_home("support", home=tmp_path / "x") == tmp_path / "x"
