from __future__ import annotations

import importlib.util
from pathlib import Path

_RETIRED_RUNTIME_MODULE = "fleetent.runtime." + "_".join(("layered", "budget"))
_RETIRED_SETUP_HELPER = "_" + "_".join(("setup", "layered", "budget"))
_RETIRED_ADD_HELPER = "_" + "_".join(("layered", "budget", "add"))


def test_retired_cross_run_budget_module_removed() -> None:
    assert importlib.util.find_spec(_RETIRED_RUNTIME_MODULE) is None


def test_loop_has_no_retired_cross_run_budget_wiring() -> None:
    src = Path("src/fleetent/runtime/loop.py").read_text(encoding="utf-8")
    assert _RETIRED_SETUP_HELPER not in src
    assert _RETIRED_ADD_HELPER not in src


def test_agent_app_has_no_retired_cross_run_budget_boot_wiring() -> None:
    src = Path("src/fleetent/runtime/agent_app.py").read_text(encoding="utf-8")
    assert "_".join(("layered", "budget")) not in src
