"""Guardrail: sandbox resource/lifecycle/skill_mount resolution does not read
platform.yaml (per-agent-sandbox-resources).

Resolving a per-agent SandboxResources from agent.yaml `sandbox.resources` MUST NOT
touch `platform.yaml` — a standalone agent owns its sandbox profile and never depends
on the machine-shared file for resources. (sandbox.mode still reads platform.yaml until
per-agent-sandbox-enablement; that is asserted there.)
"""

from __future__ import annotations

import ast
from pathlib import Path

from fleetent.agent_config import SandboxResourcesSettings
from fleetent.integrations.sandbox import config as sandbox_config
from fleetent.integrations.sandbox.config import resources_from_agent_settings


def test_resources_from_agent_settings_does_not_read_platform_yaml(monkeypatch) -> None:
    # Point platform_yaml_path at a poisoned path; if resource resolution touched it the
    # build would blow up. It must not be consulted at all.
    import fleetent.paths as paths

    def _boom() -> Path:
        raise AssertionError("sandbox resource resolution must not read platform.yaml")

    monkeypatch.setattr(paths, "platform_yaml_path", _boom)
    # Also neutralise the module-level SETTINGS_PATH so a stale binding can't be used.
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", Path("/nonexistent/poison.yaml"))

    res = resources_from_agent_settings(
        SandboxResourcesSettings(network="public_only", memory=512)
    )
    assert res.memory == 512


def test_removed_platform_yaml_resource_loaders_are_gone() -> None:
    # The machine-shared platform.yaml resource/lifecycle/skill_mount loaders are removed.
    for name in (
        "load_sandbox_resources",
        "build_resources_by_scope",
        "load_sandbox_lifecycle",
        "load_skill_mount_config",
    ):
        assert not hasattr(sandbox_config, name), f"{name} should be removed (per-agent now)"


def test_config_module_resource_path_has_no_settings_path_reads_for_resources() -> None:
    # _resources_from_section / resources_from_agent_settings must not reference SETTINGS_PATH.
    src = Path(sandbox_config.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fn in ("resources_from_agent_settings", "_resources_from_section"):
        node = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn
        )
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert "SETTINGS_PATH" not in names, f"{fn} must not read SETTINGS_PATH"
