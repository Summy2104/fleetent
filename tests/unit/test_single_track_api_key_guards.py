"""Unit guard tests: single-track API key cleanup (task 2.3).

Asserts that after retire-legacy-api-key-and-agent-rename:
  - user_store.py has no _get_by_legacy_key or users.api_key lookup paths
  - identity.py has no _legacy_key_lookup
  - platform.user_management has no migrate_api_keys
  - user_store and identity have zero fleetent.platform.* imports
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "fleetent"


def _source(rel: str) -> str:
    return (_SRC / rel).read_text()


def test_user_store_has_no_legacy_key_lookup():
    src = _source("user_store.py")
    assert "_get_by_legacy_key" not in src, "user_store still references _get_by_legacy_key"
    assert "users.api_key" not in src, "user_store still references users.api_key column"
    assert "api_key = :api_key" not in src, "user_store still queries by api_key column"


def test_identity_has_no_legacy_key_lookup():
    src = _source("identity.py")
    assert "_legacy_key_lookup" not in src, "identity still has _legacy_key_lookup"
    assert "_get_by_legacy_key" not in src, "identity still references _get_by_legacy_key"
    assert "users.api_key" not in src, "identity still references users.api_key column"


def test_user_management_has_no_migrate_api_keys():
    src = _source("platform/user_management/__init__.py")
    assert "migrate_api_keys" not in src, "platform.user_management still has migrate_api_keys"


def test_user_store_has_no_platform_import():
    """user_store must never import fleetent.platform.*"""
    src = _source("user_store.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("fleetent.platform"), (
                    f"user_store imports platform: {alias.name}"
                )
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("fleetent.platform"), (
                f"user_store imports from platform: {module}"
            )


def test_identity_has_no_platform_import():
    """identity must never import fleetent.platform.*"""
    src = _source("identity.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("fleetent.platform"), (
                    f"identity imports platform: {alias.name}"
                )
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("fleetent.platform"), (
                f"identity imports from platform: {module}"
            )
