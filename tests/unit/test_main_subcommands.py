from __future__ import annotations

import importlib
import sys

import pytest

from fleetent import __main__ as cli
from fleetent.runtime import agent_app


def test_version_prints_build_commit(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("FLEETENT_BUILD_COMMIT", "5dc87584")

    cli.main(["version"])

    assert capsys.readouterr().out == "5dc87584\n"


def test_version_prints_unknown_without_build_commit(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.delenv("FLEETENT_BUILD_COMMIT", raising=False)

    cli.main(["version"])

    assert capsys.readouterr().out == "unknown\n"


def test_platform_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], str]] = []
    platform_main_module = importlib.import_module("fleetent.platform.platform_cli.main")

    def fake_main(argv: list[str] | None = None, prog: str = "fleetent platform") -> None:
        calls.append((argv or [], prog))

    monkeypatch.setattr(platform_main_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent", "platform", "validate-config", "--format", "json"])

    cli.main()

    assert calls == [(["validate-config", "--format", "json"], "fleetent platform")]


def test_admin_subcommand_fails_as_unknown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["fleetent", "admin", "validate-config"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code != 0


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
    monkeypatch.setattr("sys.argv", ["fleetent", "kb", "worker", "--poll-interval", "0.5"])

    cli.main()

    assert calls == [["--poll-interval", "0.5"]]


def test_kb_serve_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.serve", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    serve_module = importlib.import_module("fleetent.knowledge_base.serve")
    monkeypatch.setattr(serve_module, "main", fake_main)
    monkeypatch.setattr(
        "sys.argv",
        ["fleetent", "kb", "serve", "--tenant", "tenant-a", "--service-key", "env:KB_SERVICE_KEY"],
    )

    cli.main()

    assert calls == [["--tenant", "tenant-a", "--service-key", "env:KB_SERVICE_KEY"]]


def test_kb_ingest_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.ingest_cli", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    ingest_module = importlib.import_module("fleetent.knowledge_base.ingest_cli")
    monkeypatch.setattr(ingest_module, "main", fake_main)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fleetent",
            "kb",
            "ingest",
            "--config",
            "/tmp/kb-service.yaml",
            "--kb",
            "kb-a",
            "/tmp/docs",
        ],
    )

    cli.main()

    assert calls == [["--config", "/tmp/kb-service.yaml", "--kb", "kb-a", "/tmp/docs"]]


def test_kb_create_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.create_cli", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    create_module = importlib.import_module("fleetent.knowledge_base.create_cli")
    monkeypatch.setattr(create_module, "main", fake_main)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fleetent",
            "kb",
            "create",
            "--config",
            "/tmp/kb-service.yaml",
            "--kb",
            "kb-a",
            "--description",
            "Standalone KB",
        ],
    )

    cli.main()

    assert calls == [
        ["--config", "/tmp/kb-service.yaml", "--kb", "kb-a", "--description", "Standalone KB"]
    ]


def test_kb_reindex_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.reindex_cli", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    reindex_module = importlib.import_module("fleetent.knowledge_base.reindex_cli")
    monkeypatch.setattr(reindex_module, "main", fake_main)
    monkeypatch.setattr(
        "sys.argv",
        ["fleetent", "kb", "reindex", "--config", "/tmp/kb-service.yaml", "--kb", "kb-a"],
    )

    cli.main()

    assert calls == [["--config", "/tmp/kb-service.yaml", "--kb", "kb-a"]]


def test_kb_extract_subcommand_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sys.modules.pop("fleetent.knowledge_base.extract_cli", None)

    def fake_main(argv: list[str] | None = None) -> None:
        calls.append(argv or [])

    extract_module = importlib.import_module("fleetent.knowledge_base.extract_cli")
    monkeypatch.setattr(extract_module, "main", fake_main)
    monkeypatch.setattr(
        "sys.argv",
        ["fleetent", "kb", "extract", "--config", "/tmp/kb-service.yaml", "--kb", "kb-a"],
    )

    cli.main()

    assert calls == [["--config", "/tmp/kb-service.yaml", "--kb", "kb-a"]]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["fleetent", "kb", "init-config", "--tenant", "default"], None),
        (["fleetent", "kb-worker"], "Usage: fleetent"),
        (["fleetent", "kb-serve"], "Usage: fleetent"),
        (["fleetent", "kb-ingest"], "Usage: fleetent"),
        (["fleetent", "kb-create"], "Usage: fleetent"),
        (["fleetent", "kb-reindex"], "Usage: fleetent"),
        (["fleetent", "kb-extract"], "Usage: fleetent"),
        (["fleetent", "kb-service", "init-config"], "Usage: fleetent"),
    ],
)
def test_kb_subcommand_dispatch_and_legacy_names(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str | None,
) -> None:
    if argv[:3] == ["fleetent", "kb", "init-config"]:
        calls: list[list[str]] = []
        service_init_module = importlib.import_module("fleetent.knowledge_base.service_init_config")

        def fake_main(init_argv: list[str] | None = None) -> None:
            calls.append(init_argv or [])

        monkeypatch.setattr(service_init_module, "main", fake_main)
        monkeypatch.setattr("sys.argv", argv)

        cli.main()

        assert calls == [["--tenant", "default"]]
        return

    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert message in capsys.readouterr().err


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
    sys.modules.pop("fleetent.platform.platform_cli", None)

    async def fake_serve(
        agent_id: str,
        *,
        port: int | None = None,
        home: str | None = None,
        start_im: bool = True,
    ) -> None:
        return None

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support"])

    cli.main()

    assert "fleetent.platform.platform_cli" not in sys.modules


def test_tui_does_not_load_on_agent_run(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("fleetent.tui.app", None)
    sys.modules.pop("fleetent.knowledge_base.worker", None)

    async def fake_serve(
        agent_id: str,
        *,
        port: int | None = None,
        home: str | None = None,
        start_im: bool = True,
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
        start_im: bool = True,
    ) -> None:
        return None

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support"])

    cli.main()

    assert "fleetent.knowledge_base.worker" not in sys.modules


def test_agent_run_does_not_import_kb_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("fleetent.knowledge_base.serve", None)

    async def fake_serve(
        agent_id: str,
        *,
        port: int | None = None,
        home: str | None = None,
        start_im: bool = True,
    ) -> None:
        return None

    monkeypatch.setattr(agent_app, "serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["fleetent", "agent", "run", "support"])

    cli.main()

    assert "fleetent.knowledge_base.serve" not in sys.modules
