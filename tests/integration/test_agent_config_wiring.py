"""Agent config scan is wired into server startup and the CLI (file-driven-agent-config)."""

from fastapi.testclient import TestClient

import fleetent.runtime.loop as loop
from fleetent import agent_config
from fleetent import server as srv
from fleetent import user_store as us
from fleetent.integrations.sandbox import enablement as sandbox_enablement
from fleetent.integrations.sandbox.enablement import Mode


def test_lifespan_scans_agents_once(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)  # no .env / config here
    calls: list[int] = []
    monkeypatch.setattr(agent_config, "scan", lambda *a, **k: calls.append(1))
    with TestClient(srv.app):
        pass
    assert calls == [1]


def test_cli_run_sync_scans_agents(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(agent_config, "scan", lambda *a, **k: calls.append(1))

    async def _fake_run(*a, **k):
        return "ok"

    async def _fake_mode():
        return Mode.OFF

    monkeypatch.setattr(loop, "run", _fake_run)
    monkeypatch.setattr(sandbox_enablement, "get_effective_mode", _fake_mode)

    out = loop.run_sync("hi")
    assert out == "ok"
    assert calls  # scan_agents invoked on the CLI path
