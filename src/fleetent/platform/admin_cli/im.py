"""IM user admin CLI commands."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register IM user commands."""
    p_block = subparsers.add_parser(
        "block-user", help="[DEPRECATED] use the admin UI to block IM users"
    )
    p_block.add_argument("--im-user-id", required=True, type=int, help="im_users.id")


def handle(args: argparse.Namespace) -> bool:
    """Handle IM user commands."""
    if args.cmd == "block-user":
        print(
            "block-user is deprecated; block/restore IM users from the admin UI/API instead.",
            file=sys.stderr,
        )
        return True

    return False
