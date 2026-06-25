"""Group 9.1 — contract guardrails focused on the mcp-per-user-oauth2 files.

The repo-wide guardrails in ``test_module_dependency_guardrails.py`` already scan all of
``src/fleetent`` for agent→platform reverse imports and module-level ``AsyncExitStack``
singletons. These tests pin those invariants *explicitly* to the six modules this change
added / touched, so a regression in any one of them fails with a message that names the
offending file directly (rather than being diluted in the repo-wide sweep):

* ``oauth_authcode`` (PKCE / state store / code exchange / refresh — pure protocol)
* ``per_user_tokens`` (resolver seam + token store abstraction)
* ``standalone_token_store`` (SQLite-backed encrypted store)
* ``authorization`` (no-token trigger + link build + DM-delivery seam)
* ``standalone_callback`` (self-hosted callback + transparent refresh)
* ``client`` (per-user session / bearer auth / routing)

Each file MUST NOT import the platform package (the agent runtime stays decoupled,
single-direction dependency contract) and MUST NOT hold a long-lived async resource
(``AsyncExitStack`` / live connection) at module scope (owner-task lifecycle rule).
Pure AST inspection — no import side effects, no DB, no network.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MCP_DIR = Path("src/fleetent/integrations/mcp")

# The modules this change owns / touched. Their basenames map to files under _MCP_DIR.
_CHANGE_MODULES = [
    "oauth_authcode",
    "per_user_tokens",
    "standalone_token_store",
    "authorization",
    "standalone_callback",
    "client",
]


def _module_path(name: str) -> Path:
    return _MCP_DIR / f"{name}.py"


def _tree(name: str) -> ast.Module:
    path = _module_path(name)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_dotted_names(tree: ast.Module) -> set[str]:
    """Every dotted name from ``import``/``from ... import`` (including lazy, in-function)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _module_level_asyncexitstack_holders(tree: ast.Module) -> list[str]:
    """Names bound to an ``AsyncExitStack`` at *module* scope (not inside a function/class)."""
    holders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and "AsyncExitStack" in ast.dump(node.annotation):
            if isinstance(node.target, ast.Name):
                holders.append(node.target.id)
        elif isinstance(node, ast.Assign) and "AsyncExitStack" in ast.dump(node.value):
            holders.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    return holders


@pytest.mark.parametrize("name", _CHANGE_MODULES)
def test_change_module_exists(name: str) -> None:
    """Sanity: the file the guardrail scans is actually present (detector is not vacuous)."""
    assert _module_path(name).is_file(), f"missing {name}.py — guardrail would be vacuous"


@pytest.mark.parametrize("name", _CHANGE_MODULES)
def test_no_platform_import(name: str) -> None:
    """A per-user-oauth mcp module MUST NOT import fleetent.platform (direct or lazy)."""
    leaked = {
        imp for imp in _imported_dotted_names(_tree(name)) if imp.startswith("fleetent.platform")
    }
    assert not leaked, (
        f"{name}.py imports the platform package {sorted(leaked)} — agent runtime must not "
        "depend on platform (single-direction dependency contract)"
    )


@pytest.mark.parametrize("name", _CHANGE_MODULES)
def test_no_module_level_asyncexitstack(name: str) -> None:
    """No per-user-oauth mcp module may hold a module-level AsyncExitStack singleton."""
    holders = _module_level_asyncexitstack_holders(_tree(name))
    assert not holders, (
        f"{name}.py holds a module-level AsyncExitStack singleton {holders} — long-lived "
        "async resources need a per-session owner task (谁打开谁关闭)"
    )


def test_no_outbound_or_im_import_in_authorization_seam() -> None:
    """The authorization-link trigger reaches IM/outbound only through an injected seam.

    ``authorization.py`` builds + (best-effort) delivers a link, but it MUST NOT import the
    outbound/IM layer itself — delivery flows through the injected ``AuthorizationLinkDeliverer``
    seam — so the MCP client stays free of any outbound import (the spec's "no outbound/IM
    import here" contract).
    """
    imports = _imported_dotted_names(_tree("authorization"))
    forbidden = {
        imp
        for imp in imports
        if imp.startswith(("fleetent.im_gateway", "fleetent.node")) or "outbound" in imp
    }
    assert not forbidden, (
        f"authorization.py imports the IM/outbound layer {sorted(forbidden)} — delivery must "
        "go through the injected deliverer seam, not a direct import"
    )


def test_guardrail_detectors_are_not_vacuous() -> None:
    """The AST detectors catch a planted platform import + module-level AsyncExitStack."""
    planted = ast.parse(
        "from contextlib import AsyncExitStack\n"
        "import fleetent.platform.control as ctrl\n"
        "_leak: AsyncExitStack | None = None\n"
    )
    assert any(imp.startswith("fleetent.platform") for imp in _imported_dotted_names(planted))
    assert _module_level_asyncexitstack_holders(planted) == ["_leak"]
    # A function-local AsyncExitStack (same-task, scoped) must NOT be flagged.
    local = ast.parse(
        "from contextlib import AsyncExitStack\n"
        "async def f():\n    async with AsyncExitStack() as s:\n        return s\n"
    )
    assert _module_level_asyncexitstack_holders(local) == []
