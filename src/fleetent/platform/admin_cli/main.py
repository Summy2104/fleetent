"""Admin CLI entrypoint."""

import argparse
import sys

from fleetent.platform.admin_cli import (
    config_validation,
    diagnostics,
    init_config,
    kb_connectors,
    maintenance,
    nodes,
    shared_memory,
    users,
)

_COMMAND_MODULES = (
    users,
    nodes,
    kb_connectors,
    init_config,
    config_validation,
    diagnostics,
    shared_memory,
    maintenance,
)


def main(argv: list[str] | None = None, prog: str = "fleetent admin") -> None:
    """Run the fleetent admin CLI."""
    parser = argparse.ArgumentParser(prog=prog, description="User management CLI")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    for module in _COMMAND_MODULES:
        module.register(subparsers)

    if argv is None:
        argv = sys.argv[1:]

    args = parser.parse_args(argv)

    for module in _COMMAND_MODULES:
        if module.handle(args):
            return

    parser.error(f"unknown command: {args.cmd}")
