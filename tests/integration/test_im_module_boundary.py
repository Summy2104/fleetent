"""Guard: no first-party src outside the IM module imports the legacy IM shim paths.

The unified IM module (`fleetent.platform.im_gateway_management`) owns IM identity +
connectors. Legacy import paths (`fleetent.im_user_store`, `…im_gateway_management.im_*`)
remain only as re-export-only compatibility shims; first-party src must reach the module
through its canonical submodules / public API so the shims can later be deleted.
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "fleetent"
_IM_PKG = _SRC / "platform" / "im_gateway_management"

# Legacy shim module dotted paths that first-party src must no longer import.
_LEGACY_SHIMS = {
    "fleetent.im_user_store",
    "fleetent.platform.im_gateway_management.im_connector_store",
    "fleetent.platform.im_gateway_management.im_connector_config",
    "fleetent.platform.im_gateway_management.im_connector_manager",
    "fleetent.platform.im_gateway_management.im_channel_allowlist",
    "fleetent.platform.im_gateway_management.im_admin_api",
}


def _imported_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # also catch `from <pkg> import im_connector_store`
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_no_first_party_src_imports_legacy_im_shims():
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        # The IM module package itself (incl. its shim files) is allowed to reference them.
        if _IM_PKG in path.parents or path == _IM_PKG:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = _imported_modules(tree) & _LEGACY_SHIMS
        if hits:
            offenders.append(f"{path.relative_to(_SRC)}: {sorted(hits)}")
    assert not offenders, "legacy IM shim imports outside the IM module:\n" + "\n".join(offenders)
