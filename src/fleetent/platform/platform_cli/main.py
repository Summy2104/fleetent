"""Platform CLI entrypoint."""

import argparse
import sys

from fleetent.platform.platform_cli import (
    config_validation,
    diagnostics,
    init_config,
    maintenance,
    nodes,
    serve,
    upgrade,
    users,
)

_COMMAND_MODULES = (
    serve,
    upgrade,
    users,
    nodes,
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
