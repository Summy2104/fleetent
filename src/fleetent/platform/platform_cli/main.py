"""Platform CLI entrypoint."""

import argparse
import sys

from fleetent.platform.platform_cli import (
    config_validation,
    diagnostics,
    init_config,
    kb_connectors,
    maintenance,
    nodes,
    users,
)

_COMMAND_MODULES = (
    users,
    nodes,
    kb_connectors,
    init_config,
    config_validation,
    diagnostics,
    maintenance,
)


def main(argv: list[str] | None = None, prog: str = "fleetent platform") -> None:
    """Run the fleetent platform CLI."""
    parser = argparse.ArgumentParser(prog=prog, description="Platform control-plane CLI")
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
