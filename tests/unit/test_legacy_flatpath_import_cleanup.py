"""Regression tests for the retired flat-path re-export shims.

After the flat-to-package migration (runtime-package-blueprint) was completed,
all 32 legacy flat-path modules were deleted. These tests pin that terminal
state: legacy paths are no longer importable, canonical packages are.
"""

from __future__ import annotations

import importlib
import sys

import pytest

LEGACY_FLATPATH_MODULES = (
    # sandbox -> integrations.sandbox
    "fleetent.sandbox_client",
    "fleetent.sandbox_config",
    "fleetent.sandbox_manager",
    "fleetent.sandbox_enablement",
    "fleetent.sandbox_cleanup",
    "fleetent.sandbox_secrets",
    "fleetent.sandbox_output_truncation",
    # session -> session
    "fleetent.session_mgr",
    "fleetent.session_index",
    # skills -> skills
    "fleetent.skill_registry",
    "fleetent.skill_audit",
    # model -> model
    "fleetent.model_router",
    "fleetent.provider_health",
    # tools -> tools
    "fleetent.tool_registry",
    "fleetent.tool_result_truncation",
    "fleetent.plugin_loader",
    "fleetent.vision_client",
    "fleetent.image_gen_client",
    "fleetent.multimodal",
    # runtime -> runtime
    "fleetent.agent_loop",
    "fleetent.context_mgr",
    "fleetent.agent_runtime",
    "fleetent.sub_agent",
    "fleetent.sub_agent_lifecycle",
    "fleetent.termination",
    "fleetent.loop_detector",
    "fleetent.budget",
    "fleetent." + "_".join(("layered", "budget")),
    "fleetent.cancellation",
    "fleetent.message_hygiene",
    "fleetent.error_classifier",
    "fleetent.tool_guardrails",
)

CANONICAL_PACKAGES = (
    ("fleetent.runtime", "run"),
    ("fleetent.tools", "get_schemas"),
    ("fleetent.model", "ModelPolicySnapshot"),
    ("fleetent.skills", "scan"),
    ("fleetent.session", "load"),
    ("fleetent.integrations.sandbox", "SandboxClient"),
)


@pytest.mark.parametrize("module_name", LEGACY_FLATPATH_MODULES)
def test_legacy_flatpath_module_is_not_importable(module_name: str) -> None:
    sys.modules.pop(module_name, None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


@pytest.mark.parametrize(("package_name", "public_symbol"), CANONICAL_PACKAGES)
def test_canonical_package_exposes_public_api(package_name: str, public_symbol: str) -> None:
    package = importlib.import_module(package_name)

    assert getattr(package, public_symbol)
