"""Wiring tests: module path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent import eval_logger


def _assert_derivation_in_clean_env(code: str) -> None:
    """Run an import-time derivation assertion in a child interpreter.

    Constants are frozen at import. Comparing an in-process constant against a
    call-time paths.X() is fragile: an ambient FLEETENT_HOME in the developer
    shell freezes a different base than a post-delenv call resolves. A child
    interpreter with FLEETENT_HOME stripped checks constant == derivation under
    one consistent environment.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "FLEETENT_HOME"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_constants_derive_from_paths() -> None:
    _assert_derivation_in_clean_env(
        "from fleetent import eval_logger, paths; "
        "from fleetent.integrations.sandbox import config as sc, enablement as se; "
        "from fleetent.tools import builtin_tools as bt; "
        "assert eval_logger.TRACE_PATH == paths.data_dir() / 'traces.jsonl'; "
        "assert bt.GENERATED_DIR == paths.data_dir() / 'generated'; "
        "assert bt.UPLOADS_DIR == paths.data_dir() / 'uploads'; "
        "assert sc.SETTINGS_PATH == paths.platform_yaml_path(); "
        "assert se.SETTINGS_PATH == paths.platform_yaml_path()"
    )


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
