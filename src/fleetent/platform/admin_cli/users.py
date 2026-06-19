"""User-related admin CLI commands."""

from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register user commands."""
    subparsers.add_parser("seed-builtin-admin", help="Seed the built-in admin (first run)")


def handle(args: argparse.Namespace) -> bool:
    """Handle user commands."""
    if args.cmd == "seed-builtin-admin":
        from fleetent.auth import seed_builtin_admin

        result = seed_builtin_admin()
        if result is None:
            print("Built-in admin already exists.")
        else:
            admin_user, temp_password = result
            print("Built-in admin created.")
            print(f"  username:         {admin_user.name}")
            print(f"  initial_password: {temp_password}  ← change on first login, shown once")
        return True

    return False
