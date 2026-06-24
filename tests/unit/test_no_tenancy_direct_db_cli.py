"""Guardrail for platform CLI direct-write boundaries."""

from __future__ import annotations

import argparse
import importlib


def test_no_tenancy_direct_db_cli() -> None:
    platform_cli = importlib.import_module("fleetent.platform.platform_cli.main")

    parser = argparse.ArgumentParser(prog="fleetent platform")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    for module in platform_cli._COMMAND_MODULES:
        module.register(subparsers)

    module_names = {module.__name__ for module in platform_cli._COMMAND_MODULES}
    subcommands = set(subparsers.choices)

    assert "fleetent.platform.platform_cli.tenancy" not in module_names
    for command in {
        "create-tenant",
        "list-tenants",
        "create-team",
        "set-user-tenant",
        "set-approver",
    }:
        assert command not in subcommands
