"""Wiring tests: module path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent import eval_logger, paths
from fleetent.integrations.sandbox import config as sandbox_config
from fleetent.integrations.sandbox import enablement as sandbox_enablement
from fleetent.tools import builtin_tools


def test_constants_derive_from_paths(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    assert paths.data_dir() / "traces.jsonl" == eval_logger.TRACE_PATH
    assert paths.data_dir() / "generated" == builtin_tools.GENERATED_DIR
    assert paths.data_dir() / "uploads" == builtin_tools.UPLOADS_DIR
    assert paths.settings_yaml_path() == sandbox_config.SETTINGS_PATH
    assert paths.settings_yaml_path() == sandbox_enablement.SETTINGS_PATH


def test_fleetent_home_redirects_on_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    # eval_logger has no import side effects, so reloading is safe.
    reloaded = importlib.reload(eval_logger)
    try:
        assert home / "data" / "traces.jsonl" == reloaded.TRACE_PATH
    finally:
        monkeypatch.delenv("FLEETENT_HOME", raising=False)
        importlib.reload(eval_logger)


def test_module_constant_still_patchable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "isolated" / "traces.jsonl"
    monkeypatch.setattr(eval_logger, "TRACE_PATH", target)
    assert target == eval_logger.TRACE_PATH
