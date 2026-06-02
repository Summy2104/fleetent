"""Regression tests for retired top-level compatibility shims."""

from __future__ import annotations

import importlib
import sys

import pytest

LEGACY_MODULES = (
    "fleetent.agent_policy",
    "fleetent.audit_log",
    "fleetent.blocklist",
    "fleetent.permission_gate",
    "fleetent.quota",
    "fleetent.mcp_client",
    "fleetent.sandbox_client",
)

CANONICAL_MODULES = (
    "fleetent.governance.agent_policy",
    "fleetent.governance.audit_log",
    "fleetent.governance.blocklist",
    "fleetent.governance.permission_gate",
    "fleetent.governance.quota",
    "fleetent.integrations.mcp",
    "fleetent.integrations.mcp.client",
    "fleetent.integrations.sandbox",
    "fleetent.integrations.sandbox.client",
)


@pytest.mark.parametrize("module_name", CANONICAL_MODULES)
def test_canonical_cleanup_imports_remain_available(module_name: str) -> None:
    assert importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", LEGACY_MODULES)
def test_retired_top_level_shims_are_not_importable(module_name: str) -> None:
    sys.modules.pop(module_name, None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
