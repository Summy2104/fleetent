"""Admin CLI entrypoint."""

import argparse

from fleetent.platform.admin_cli import (
    agents,
    diagnostics,
    im,
    im_connectors,
    init_config,
    kb_connectors,
    observability,
    schedules,
    shared_memory,
    users,
)

_COMMAND_MODULES = (
    users,
    im,
    im_connectors,
    agents,
    schedules,
    kb_connectors,
    init_config,
    diagnostics,
    observability,
    shared_memory,
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
