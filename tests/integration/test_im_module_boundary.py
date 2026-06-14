"""Guard: peer modules reach the IM module through its public API."""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "fleetent"
_IM_PKG = _SRC / "platform" / "im_gateway_management"

# Canonical internal submodules. Peer modules MUST reach the IM module through its
# package public API (`fleetent.platform.im_gateway_management`), never these files.
_PKG = "fleetent.platform.im_gateway_management"
_CANONICAL_SUBMODULES = {
    f"{_PKG}.identity",
}

# server.py is the FastAPI composition root.
_COMPOSITION_ROOT = {_SRC / "server.py"}

# Legacy re-export-only shims live outside the package; they exist precisely to forward to
# the canonical submodule, so they are exempt from the public-API rule.
_SHIM_FILES = {_SRC / "im_user_store.py"}


def _imported_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # also catch `from <pkg> import identity`
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_peer_modules_use_im_public_api_not_internal_submodules():
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        if (
            _IM_PKG in path.parents
            or path == _IM_PKG
            or path in _COMPOSITION_ROOT
            or path in _SHIM_FILES
        ):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = _imported_modules(tree) & _CANONICAL_SUBMODULES
        if hits:
            offenders.append(f"{path.relative_to(_SRC)}: {sorted(hits)}")
    assert not offenders, (
        "peer modules must call the IM package public API, not internal submodules:\n"
        + "\n".join(offenders)
    )
