"""Admin CLI entrypoint."""

import argparse

from fleetent.platform.admin_cli import (
    agents,
    diagnostics,
    im,
    init_config,
    kb_connectors,
    observability,
    schedules,
    users,
)

_COMMAND_MODULES = (
    users,
    im,
    agents,
    schedules,
    kb_connectors,
    init_config,
    diagnostics,
    observability,
)


def main() -> None:
    """Run the fleetent admin CLI."""
    parser = argparse.ArgumentParser(prog="fleetent-admin", description="User management CLI")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    for module in _COMMAND_MODULES:
        module.register(subparsers)

    args = parser.parse_args()

    for module in _COMMAND_MODULES:
        if module.handle(args):
            return

    parser.error(f"unknown command: {args.cmd}")
