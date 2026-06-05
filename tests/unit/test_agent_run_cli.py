"""`fleetent agent run <agent-id> [--port N]` CLI + foreground serve."""

from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.__main__ as cli
from fleetent.runtime import agent_app


def test_parse_agent_run_defaults():
    ns = cli._parse_agent_run(["support"])
    assert ns.agent_id == "support"
    assert ns.port is None
    assert ns.home is None


def test_parse_agent_run_with_port_and_home(tmp_path):
    ns = cli._parse_agent_run(["support", "--port", "8770", "--home", str(tmp_path)])
    assert ns.agent_id == "support"
    assert ns.port == 8770
    assert ns.home == str(tmp_path)


def test_main_dispatches_agent_run(monkeypatch):
    served = {}

    async def fake_serve(agent_id, *, port=None, home=None):
        served["agent_id"] = agent_id
        served["port"] = port

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support", "--port", "8770"])
    cli.main()
    assert served == {"agent_id": "support", "port": 8770}


def test_main_oneshot_still_works(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run", lambda text, **k: f"echo:{text}")
    monkeypatch.setattr("sys.argv", ["fleetent", "hello", "world"])
    cli.main()
    assert "echo:hello world" in capsys.readouterr().out


async def test_serve_with_port_mounts_http(monkeypatch):
    rt = MagicMock()
    rt.app = MagicMock()
    rt.stop = AsyncMock()
    monkeypatch.setattr(agent_app, "boot", AsyncMock(return_value=rt))
    waited = {"forever": False}
    monkeypatch.setattr(
        agent_app,
        "_wait_forever",
        AsyncMock(side_effect=lambda: waited.__setitem__("forever", True)),
    )

    fake_server = MagicMock()
    fake_server.serve = AsyncMock()
    with patch("uvicorn.Server", return_value=fake_server) as server_cls, patch("uvicorn.Config"):
        await agent_app.serve("support", port=8770)

    server_cls.assert_called_once()  # HTTP listener constructed
    fake_server.serve.assert_awaited_once()
    assert waited["forever"] is False  # did not take the IM-only block path
    rt.stop.assert_awaited_once()


async def test_serve_without_port_opens_no_http(monkeypatch):
    rt = MagicMock()
    rt.app = None
    rt.stop = AsyncMock()
    monkeypatch.setattr(agent_app, "boot", AsyncMock(return_value=rt))
    monkeypatch.setattr(agent_app, "_wait_forever", AsyncMock())

    with patch("uvicorn.Server") as server_cls:
        await agent_app.serve("support")

    server_cls.assert_not_called()  # no HTTP listener without --port
    agent_app._wait_forever.assert_awaited_once()
    rt.stop.assert_awaited_once()
