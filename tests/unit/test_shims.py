from __future__ import annotations

import importlib
import sys

from fleetent import _shims


def test_admin_shim_prints_to_stderr_and_rewrites_argv(
    monkeypatch, capsys
) -> None:
    main_module = importlib.import_module("fleetent.__main__")
    captured_argv: list[str] = []

    def fake_main() -> None:
        captured_argv.extend(sys.argv)

    monkeypatch.setattr(main_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent-admin", "validate-config", "--format", "json"])

    _shims.fleetent_admin_shim()

    assert captured_argv == ["fleetent", "admin", "validate-config", "--format", "json"]
    assert "Deprecated: 'fleetent-admin' → use 'fleetent admin'." in capsys.readouterr().err


def test_node_shim_prints_to_stderr(monkeypatch, capsys) -> None:
    main_module = importlib.import_module("fleetent.__main__")
    captured_argv: list[str] = []

    def fake_main() -> None:
        captured_argv.extend(sys.argv)

    monkeypatch.setattr(main_module, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["fleetent-node"])

    _shims.fleetent_node_shim()

    assert captured_argv == ["fleetent", "node", "start"]
    assert "Deprecated: 'fleetent-node' → use 'fleetent node start'." in capsys.readouterr().err
