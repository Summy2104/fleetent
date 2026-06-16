"""Guardrail: sandbox enablement no longer reads platform.yaml for mode
(per-agent-sandbox-enablement).

`integrations/sandbox/enablement.py` derives ON/OFF purely from the backend probe;
the tri-state `sandbox.mode` read (load_sandbox_mode / SETTINGS_PATH) is gone.
(Backend selection's optional platform.yaml default is out of scope — agent.yaml-first
with a docker fallback.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import fleetent.integrations.sandbox.enablement as se


def test_enablement_module_does_not_reference_platform_yaml() -> None:
    src = Path(se.__file__).read_text(encoding="utf-8")
    assert "platform_yaml_path" not in src
    assert "SETTINGS_PATH" not in src
    # The tri-state mode loader and its YAML read are removed.
    assert "load_sandbox_mode" not in src
    assert "import yaml" not in src


def test_enablement_has_no_tristate_symbols() -> None:
    assert not hasattr(se, "load_sandbox_mode")
    assert not hasattr(se, "resolve_effective_mode")
    assert not hasattr(se, "SETTINGS_PATH")
    assert {m.value for m in se.Mode} == {"off", "on"}


def test_get_effective_mode_does_not_read_platform_yaml(monkeypatch) -> None:
    import fleetent.paths as paths

    def _boom() -> Path:
        raise AssertionError("enablement must not read platform.yaml")

    monkeypatch.setattr(paths, "platform_yaml_path", _boom)
    # Static check the function body references no SETTINGS_PATH/platform read.
    tree = ast.parse(Path(se.__file__).read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_effective_mode"
    )
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "SETTINGS_PATH" not in names
