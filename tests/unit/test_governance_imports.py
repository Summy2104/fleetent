import ast
import importlib
from pathlib import Path

GOVERNANCE_PUBLIC_APIS = {
    "permission_gate": {
        "ApprovalResult",
        "PermissionGate",
        "_default_gate",
        "cleanup_stale_approvals",
        "list_approvals",
        "_init_db",
        "DB_PATH",
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
    "audit_log": {
        "DB_PATH",
        "search_audit",
        "write_audit",
        "_init_db",
    },
    "blocklist": {
        "DB_PATH",
        "batch_block",
        "block_user",
        "is_registration_blocked",
        "unblock_user",
        "_disable_im_accounts",
        "_ban_registration",
        "_init_db",
    },
    "agent_policy": {"check_tool_access"},
}


def test_governance_package_and_canonical_modules_import():
    importlib.import_module("fleetent.governance")

    for module_name in GOVERNANCE_PUBLIC_APIS:
        importlib.import_module(f"fleetent.governance.{module_name}")


def test_legacy_governance_imports_reexport_canonical_public_api():
    for module_name, public_names in GOVERNANCE_PUBLIC_APIS.items():
        canonical = importlib.import_module(f"fleetent.governance.{module_name}")
        legacy = importlib.import_module(f"fleetent.{module_name}")

        assert set(legacy.__all__) == public_names
        for public_name in public_names:
            assert getattr(legacy, public_name) is getattr(canonical, public_name)


def test_legacy_governance_shims_only_reexport_public_names():
    root = Path(__file__).parents[2] / "src" / "fleetent"

    for module_name, public_names in GOVERNANCE_PUBLIC_APIS.items():
        module_path = root / f"{module_name}.py"
        tree = ast.parse(module_path.read_text())
        statements = [node for node in tree.body if not isinstance(node, ast.Expr)]

        assert len(statements) == 2
        assert isinstance(statements[0], ast.ImportFrom)
        assert statements[0].module == f"fleetent.governance.{module_name}"
        assert {alias.name for alias in statements[0].names} == public_names
        assert isinstance(statements[1], ast.Assign)
        assert statements[1].targets[0].id == "__all__"
