"""Dependency guardrail: agent-side identity path must not import fleetent.platform.*.

Task 2.1 — these tests fail until user_store.authenticate no longer has an
unconditional platform import.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from unittest.mock import patch


def _src_path(rel: str) -> Path:
    here = Path(__file__).parents[2]  # repo root inside worktree
    return here / "src" / "fleetent" / rel


def _collect_top_level_imports(source: str) -> list[str]:
    """Return dotted module names from all import statements at any level in source."""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


# ── Static AST checks (catch lazy imports too) ─────────────────────────────


def test_identity_module_no_platform_import_static():
    """identity.py MUST NOT import fleetent.platform.* at any level."""
    src = _src_path("identity.py").read_text()
    imports = _collect_top_level_imports(src)
    platform_imports = [i for i in imports if i.startswith("fleetent.platform")]
    assert platform_imports == [], (
        f"identity.py has forbidden platform imports: {platform_imports}"
    )


def test_user_store_authenticate_no_platform_import_static():
    """user_store.authenticate must not have a static platform import after #1 fix."""
    src = _src_path("user_store.py").read_text()
    # Check specifically the authenticate function body — parse and walk its node
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "authenticate":
            func_src = ast.unparse(node)
            assert "fleetent.platform" not in func_src, (
                "user_store.authenticate still references fleetent.platform — #1 not fixed"
            )
            return
    # If authenticate doesn't exist at all, that's also acceptable.


def test_im_gateway_access_no_platform_import_static():
    """im_gateway/access.py must not import fleetent.platform.*."""
    src = _src_path("im_gateway/access.py").read_text()
    imports = _collect_top_level_imports(src)
    platform_imports = [i for i in imports if i.startswith("fleetent.platform")]
    assert platform_imports == [], (
        f"im_gateway/access.py has forbidden platform imports: {platform_imports}"
    )


# ── Runtime check: importing identity doesn't pull in platform ─────────────


def test_importing_identity_does_not_load_platform_modules():
    """Importing fleetent.identity must not cause fleetent.platform.* to load."""
    # Purge cached platform modules to get a clean slate.
    for key in list(sys.modules):
        if key.startswith("fleetent.platform"):
            del sys.modules[key]
    # Also purge identity so we get a fresh import.
    for key in list(sys.modules):
        if key in ("fleetent.identity",):
            del sys.modules[key]

    import fleetent.identity  # noqa: F401

    loaded = [k for k in sys.modules if k.startswith("fleetent.platform")]
    assert loaded == [], f"platform modules loaded by importing fleetent.identity: {loaded}"

