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


def test_chat_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    tui_app_module = importlib.import_module("fleetent.tui.app")

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    monkeypatch.setattr(tui_app_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "chat", "--help"])

    cli.main()

    assert calls == [["--help"]]


def test_kb_worker_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.worker", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    worker_module = importlib.import_module("fleetent.knowledge_base.worker")
    monkeypatch.setattr(worker_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "kb-worker", "--poll-interval", "0.5"])

    cli.main()

    assert calls == [["--poll-interval", "0.5"]]


def test_tui_no_longer_dispatches_client(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[str] = []
    sys.modules.pop("fleetent.tui.app", None)

    def fake_run(user_input: str) -> str:
        prompts.append(user_input)
        return "ok"

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["fleetent", "tui", "--help"])

    cli.main()

    assert prompts == ["tui --help"]
    assert "fleetent.tui.app" not in sys.modules


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
    sys.modules.pop("fleetent.knowledge_base.worker", None)

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


def test_agent_run_does_not_import_kb_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("fleetent.knowledge_base.worker", None)

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

    assert "fleetent.knowledge_base.worker" not in sys.modules
