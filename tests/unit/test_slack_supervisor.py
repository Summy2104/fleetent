"""Per-agent Slack connector supervisor: start/stop/reload keyed by agent."""

import asyncio

import yaml

from fleetent import agent_config
from fleetent.im_gateway import slack_supervisor


def _write(root, name, bot_env, app_env, channels=None):
    doc = {
        "name": name,
        "version": 1,
        "connectors": {
            "slack": {
                "bot_token_env": bot_env,
                "app_token_env": app_env,
                "channels": channels or [],
            }
        },
    }
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _supervisor(started):
    async def fake_runner(agent_name, owner_id, cfg):
        started.append((agent_name, owner_id, cfg))
        await asyncio.Event().wait()  # stay connected until cancelled

    return slack_supervisor.SlackSupervisor(runner=fake_runner, owner_id_provider=lambda: "ownerX")


async def test_starts_one_connection_per_slack_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("SUP_BOT", "xoxb-1")
    monkeypatch.setenv("SUP_APP", "xapp-1")
    monkeypatch.setenv("SAL_BOT", "xoxb-2")
    monkeypatch.setenv("SAL_APP", "xapp-2")
    _write(tmp_path, "support", "SUP_BOT", "SUP_APP", channels=["C1"])
    _write(tmp_path, "sales", "SAL_BOT", "SAL_APP")
    agent_config.scan(tmp_path)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)

    assert sup.running() == {"support", "sales"}
    names = {s[0] for s in started}
    assert names == {"support", "sales"}
    # config carries resolved tokens + channels, and the owner from the provider
    sup_cfg = next(s for s in started if s[0] == "support")
    assert sup_cfg[1] == "ownerX"
    assert sup_cfg[2]["bot_token"] == "xoxb-1" and sup_cfg[2]["channels"] == ["C1"]
    await sup.stop_all()


async def test_missing_token_isolates_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SAL_BOT", "xoxb-2")
    monkeypatch.setenv("SAL_APP", "xapp-2")
    # support's env vars are intentionally unset
    _write(tmp_path, "support", "MISSING_BOT", "MISSING_APP")
    _write(tmp_path, "sales", "SAL_BOT", "SAL_APP")
    agent_config.scan(tmp_path)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)

    assert sup.running() == {"sales"}
    assert sup.status().get("support") == "unconfigured"
    await sup.stop_all()


async def test_reload_adds_and_removes(tmp_path, monkeypatch):
    monkeypatch.setenv("B", "xoxb")
    monkeypatch.setenv("A", "xapp")
    _write(tmp_path, "support", "B", "A")
    agent_config.scan(tmp_path)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)
    assert sup.running() == {"support"}

    _write(tmp_path, "sales", "B", "A")
    agent_config.scan(tmp_path)
    await sup.reload()
    await asyncio.sleep(0)
    assert sup.running() == {"support", "sales"}

    import shutil

    shutil.rmtree(tmp_path / "sales")
    agent_config.scan(tmp_path)
    await sup.reload()
    await asyncio.sleep(0)
    assert sup.running() == {"support"}
    await sup.stop_all()


async def test_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("B", "xoxb")
    monkeypatch.setenv("A", "xapp")
    _write(tmp_path, "support", "B", "A")
    agent_config.scan(tmp_path)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)
    await sup.stop("support")
    assert sup.running() == set()
    assert sup.status().get("support") == "stopped"
