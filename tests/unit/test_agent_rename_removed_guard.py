"""Unit guard: rename_agent write paths are deleted (task 3.1).

Asserts that after retire-legacy-api-key-and-agent-rename:
  - agent_store has no rename_agent function
  - agent_admin_store has no rename function
  - agent_console_api.rename_agent_def is None (stub with no impl)
  - agent_console_api.UpdateBody has no 'name' field (rename path deleted)
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "fleetent"


def _source(rel: str) -> str:
    return (_SRC / rel).read_text()


def test_agent_store_has_no_rename_agent():
    src = _source("agent_store.py")
    assert "def rename_agent" not in src, "agent_store still has rename_agent"
    assert "rename_agent" not in src, "agent_store still references rename_agent"


def test_agent_admin_store_has_no_rename():
    src = _source("platform/agent_management_console/agent_admin_store.py")
    assert "def rename(" not in src, "agent_admin_store still has rename()"
    assert "UPDATE agent_admin_state SET agent_name" not in src, (
        "agent_admin_store still has rename SQL"
    )


def test_console_api_rename_agent_def_is_none():
    """rename_agent_def stub must be None (dead code removed, stub reset to None)."""
    from fleetent.platform.agent_management_console import agent_console_api

    assert agent_console_api.rename_agent_def is None, (
        "rename_agent_def is not None — rename path still wired"
    )


def test_update_body_has_no_name_field():
    """UpdateBody.name (the rename trigger) must be removed."""
    src = _source("platform/agent_management_console/agent_console_api.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "UpdateBody":
            for item in ast.walk(node):
                if isinstance(item, ast.AnnAssign):
                    target = item.target
                    if isinstance(target, ast.Name) and target.id == "name":
                        raise AssertionError("UpdateBody still has a 'name' field")
            return
    # UpdateBody not found → ok (already removed entirely)
