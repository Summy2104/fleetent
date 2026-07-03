"""Tests for fleetent platform serve command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from fleetent.platform.platform_cli.main import main as platform_cli_main


def _run_platform(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            platform_cli_main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_serve_calls_uvicorn_with_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_run(
        app: str, *, host: str, port: int, reload: bool = False, log_level: str = "info"
    ) -> None:
        calls.append(
            {"app": app, "host": host, "port": port, "reload": reload, "log_level": log_level}
        )

    import fleetent.platform.platform_cli.serve as serve_module

    monkeypatch.setattr(serve_module, "_uvicorn_run", fake_run)

    out, err, code = _run_platform("serve", "--host", "127.0.0.1", "--port", "8767")

    assert code == 0
    assert err == ""
    assert calls == [
        {
            "app": "fleetent.server:app",
            "host": "127.0.0.1",
            "port": 8767,
            "reload": False,
            "log_level": "info",
        }
    ]


def test_serve_default_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_run(
        app: str, *, host: str, port: int, reload: bool = False, log_level: str = "info"
    ) -> None:
        calls.append(
            {"app": app, "host": host, "port": port, "reload": reload, "log_level": log_level}
        )

    import fleetent.platform.platform_cli.serve as serve_module

    monkeypatch.setattr(serve_module, "_uvicorn_run", fake_run)

    _run_platform("serve")

    assert len(calls) == 1
    assert calls[0]["app"] == "fleetent.server:app"
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 8765
    assert calls[0]["reload"] is False
    assert calls[0]["log_level"] == "info"


def test_serve_reload_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_run(
        app: str, *, host: str, port: int, reload: bool = False, log_level: str = "info"
    ) -> None:
        calls.append(
            {"app": app, "host": host, "port": port, "reload": reload, "log_level": log_level}
        )

    import fleetent.platform.platform_cli.serve as serve_module

    monkeypatch.setattr(serve_module, "_uvicorn_run", fake_run)

    _run_platform("serve", "--reload")

    assert calls[0]["reload"] is True
    assert calls[0]["log_level"] == "info"
