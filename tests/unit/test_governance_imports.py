import importlib
import inspect
import sys

import pytest

GOVERNANCE_PUBLIC_APIS = {
    "permission_gate": {
        "ApprovalResult",
        "PermissionGate",
        "_default_gate",
        "cleanup_stale_approvals",
        "list_approvals",
    },
    "quota": {
        "DB_PATH",
        "check_quota",
        "record_usage",
        "set_quota",
        "_get_quota",
        "_get_usage",
        "_init_db",
    },
    "blocklist": {
        "DB_PATH",
        "ban_registration",
        "is_registration_blocked",
        "_init_db",
    },
    "agent_policy": {"check_tool_access"},
}


def test_governance_package_and_canonical_modules_import():
    importlib.import_module("fleetent.governance")

    for module_name in GOVERNANCE_PUBLIC_APIS:
        importlib.import_module(f"fleetent.governance.{module_name}")


def test_governance_canonical_public_api_remains_available():
    for module_name, public_names in GOVERNANCE_PUBLIC_APIS.items():
        canonical = importlib.import_module(f"fleetent.governance.{module_name}")

        for public_name in public_names:
            assert getattr(canonical, public_name)


@pytest.mark.parametrize("module_name", GOVERNANCE_PUBLIC_APIS)
def test_governance_modules_do_not_import_platform(module_name: str) -> None:
    """agent-runtime governance MUST NOT depend on the platform control plane."""
    module = importlib.import_module(f"fleetent.governance.{module_name}")
    source = inspect.getsource(module)
    assert "fleetent.platform" not in source


@pytest.mark.parametrize("module_name", GOVERNANCE_PUBLIC_APIS)
def test_legacy_governance_imports_are_removed(module_name: str) -> None:
    sys.modules.pop(f"fleetent.{module_name}", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"fleetent.{module_name}")


def test_permission_gate_does_not_import_user_store() -> None:
    """permission_gate MUST NOT import fleetent.user_store (agent→platform leak #1)."""
    module = importlib.import_module("fleetent.governance.permission_gate")
    source = inspect.getsource(module)
    assert "fleetent.user_store" not in source
    assert "user_store" not in source
