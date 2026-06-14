"""Per-agent Slack connector supervisor: start/stop/reload keyed by agent."""

import asyncio

import yaml

from fleetent import agent_config
from fleetent.im_gateway import slack_supervisor


def _write(root, name, bot_env, app_env, allow_groups=None):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "im": {
            "slack": {
                "bot_token_env": bot_env,
                "app_token_env": app_env,
                "access": {"allow_groups": allow_groups or []},
            }
        },
    }
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _supervisor(started):
    async def fake_runner(agent_name, cfg):
        started.append((agent_name, cfg))
        await asyncio.Event().wait()  # stay connected until cancelled

    return slack_supervisor.SlackSupervisor(runner=fake_runner)


async def test_starts_one_connection_per_slack_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("SUP_BOT", "xoxb-1")
    monkeypatch.setenv("SUP_APP", "xapp-1")
    monkeypatch.setenv("SAL_BOT", "xoxb-2")
    monkeypatch.setenv("SAL_APP", "xapp-2")
    _write(tmp_path, "support", "SUP_BOT", "SUP_APP", allow_groups=["C1"])
    _write(tmp_path, "sales", "SAL_BOT", "SAL_APP")
    agent_config.scan(tmp_path)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)

    assert sup.running() == {"support", "sales"}
    names = {s[0] for s in started}
    assert names == {"support", "sales"}
    # runner receives (agent_name, config) — no owner_id is threaded
    sup_cfg = next(s for s in started if s[0] == "support")
    assert sup_cfg[1]["bot_token"] == "xoxb-1"
    await sup.stop_all()


async def test_supervisor_reads_no_platform_user_store(tmp_path, monkeypatch):
    """Standalone supervisor must not resolve owner_id via the platform users table."""
    monkeypatch.setenv("B", "xoxb")
    monkeypatch.setenv("A", "xapp")
    _write(tmp_path, "support", "B", "A")
    agent_config.scan(tmp_path)

    from fleetent import user_store

    def _boom() -> str:
        raise AssertionError("supervisor must not read the platform users table")

    monkeypatch.setattr(user_store, "admin_owner_id", _boom)

    started: list = []
    sup = _supervisor(started)
    await sup.start_from_index()
    await asyncio.sleep(0)

    assert sup.running() == {"support"}
    assert sup.status().get("support") != "error"
    assert started and started[0][0] == "support"
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
