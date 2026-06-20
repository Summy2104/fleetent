from __future__ import annotations

import importlib
import sys

import pytest

from fleetent import __main__ as cli
from fleetent.runtime import agent_app


def test_admin_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], str]] = []
    admin_main_module = importlib.import_module("fleetent.platform.admin_cli.main")

    def fake_main(argv: list[str] | None = None, prog: str = "fleetent admin") -> None:
        calls.append((argv or [], prog))

    monkeypatch.setattr(admin_main_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "admin", "validate-config", "--format", "json"])

    cli.main()

    assert calls == [(["validate-config", "--format", "json"], "fleetent admin")]


def test_node_start_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}
    node_app_module = importlib.import_module("fleetent.node.app")

    def fake_main() -> None:
        called["value"] = True

    monkeypatch.setattr(node_app_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "node", "start"])

    cli.main()

    assert called["value"] is True


def test_node_without_start_errors(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["fleetent", "node"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert "Usage: fleetent node start" in capsys.readouterr().err


def test_tui_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    tui_app_module = importlib.import_module("fleetent.tui.app")

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    monkeypatch.setattr(tui_app_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "tui", "--help"])

    cli.main()

    assert calls == [["--help"]]


def test_agent_run_does_not_import_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("fleetent.platform.admin_cli", None)

    async def fake_serve(
        agent_id: str,
        *,
        port: int | None = None,
        home: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support"])

    cli.main()

    assert "fleetent.platform.admin_cli" not in sys.modules


def test_tui_does_not_load_on_agent_run(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("fleetent.tui.app", None)

    async def fake_serve(
        agent_id: str,
        *,
        port: int | None = None,
        home: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support"])

    cli.main()

    assert "fleetent.tui.app" not in sys.modules
