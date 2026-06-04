"""Wiring tests: module path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent import eval_logger, paths
from fleetent.integrations.sandbox import config as sandbox_config
from fleetent.integrations.sandbox import enablement as sandbox_enablement
from fleetent.tools import builtin_tools


def test_constants_derive_from_paths() -> None:
    assert eval_logger.TRACE_PATH == paths.data_dir() / "traces.jsonl"
    assert builtin_tools.GENERATED_DIR == paths.data_dir() / "generated"
    assert builtin_tools.UPLOADS_DIR == paths.data_dir() / "uploads"
    assert sandbox_config.SETTINGS_PATH == paths.settings_yaml_path()
    assert sandbox_enablement.SETTINGS_PATH == paths.settings_yaml_path()


def test_fleetent_home_redirects_on_reload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    # eval_logger has no import side effects, so reloading is safe.
    reloaded = importlib.reload(eval_logger)
    try:
        assert reloaded.TRACE_PATH == home / "data" / "traces.jsonl"
    finally:
        monkeypatch.delenv("FLEETENT_HOME", raising=False)
        importlib.reload(eval_logger)


def test_module_constant_still_patchable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "isolated" / "traces.jsonl"
    monkeypatch.setattr(eval_logger, "TRACE_PATH", target)
    assert eval_logger.TRACE_PATH == target
