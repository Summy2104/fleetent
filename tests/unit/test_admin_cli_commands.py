from __future__ import annotations

import argparse
import importlib

admin_main = importlib.import_module("fleetent.platform.admin_cli.main")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetent admin")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    for module in admin_main._COMMAND_MODULES:
        module.register(subparsers)
    return parser


def test_removed_commands_absent() -> None:
    parser = _build_parser()
    top_level = parser._subparsers._group_actions[0].choices

    for removed in (
        "create-user",
        "list-users",
        "rotate-key",
        "block-user",
        "observability",
        "update-agent",
        "list-agent-versions",
        "activate-agent-version",
        "show-agent",
        "assign-user",
        "unassign-user",
        "set-default-agent",
    ):
        assert removed not in top_level

    kb_choices = top_level["kb"]._subparsers._group_actions[0].choices
    assert "connectors" not in kb_choices
    assert "extract-entities" in kb_choices


def test_command_modules_has_no_empty_module() -> None:
    module_names = {module.__name__.rsplit(".", 1)[-1] for module in admin_main._COMMAND_MODULES}

    assert "im" not in module_names
    assert "agents" not in module_names
