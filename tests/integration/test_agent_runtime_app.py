"""Standalone agent runtime: boot one agent home, bind IM, optional HTTP — no platform."""

import yaml
from fastapi.testclient import TestClient

import fleetent.runtime.loop as loop
import fleetent.user_store as us
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
    doc = {
        "name": name,
        "version": 1,
        "system_prompt": "I am support.",
        "models": agent_config.default_models().model_dump(mode="json"),
    }
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


def test_chat_streams_and_applies_agent(tmp_path, monkeypatch):
    # Functional /chat: proves the route is wired (not just present) and applies the
    # home agent's config to run_stream. (Regression guard: an earlier annotation bug
    # made the routes build but fail at request time.)
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    user = us.create_user("ChatUser")
    home = _write_home(tmp_path, allowed_tools=["shell"], allowed_skills=["weather"])
    agent_config.scan_home(home)

    captured = {}

    async def fake_run_stream(message, **kwargs):
        captured["message"] = message
        captured.update(kwargs)
        yield {"type": "done", "content": "streamed-reply"}

    monkeypatch.setattr(loop, "run_stream", fake_run_stream)

    app = agent_app.build_app("support")
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )

    assert resp.status_code == 200
    assert "streamed-reply" in resp.text
    assert captured["agent_name"] == "support"
    assert captured["system_prompt"] == "I am support."
    assert "shell" in captured["allowed_tools"]
    assert captured["allowed_skills"] == ["weather"]


def test_chat_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    app = agent_app.build_app("support")
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_resolve_home_uses_fleetent_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert agent_app.resolve_home("support") == tmp_path / "support"
    # explicit override wins
    assert agent_app.resolve_home("support", home=tmp_path / "x") == tmp_path / "x"
