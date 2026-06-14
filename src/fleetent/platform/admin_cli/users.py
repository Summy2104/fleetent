"""User-related admin CLI commands."""

from __future__ import annotations

import argparse
import sys

from fleetent.user_store import create_user, list_users, rotate_key


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register user commands."""
    p_create = subparsers.add_parser("create-user", help="Create a new user")
    p_create.add_argument("--name", required=True, help="Display name")

    subparsers.add_parser("list-users", help="List all users")

    p_rotate = subparsers.add_parser("rotate-key", help="Rotate a user's API key")
    p_rotate.add_argument("--user-id", required=True, help="User UUID")

    subparsers.add_parser("seed-builtin-admin", help="Seed the built-in admin (first run)")


def handle(args: argparse.Namespace) -> bool:
    """Handle user commands."""
    if args.cmd == "create-user":
        user, api_key = create_user(args.name)
        print("User created.")
        print(f"  id:      {user.id}")
        print(f"  name:    {user.name}")
        print(f"  api_key: {api_key}  ← save this, shown once")
        return True

    if args.cmd == "list-users":
        users = list_users()
        if not users:
            print("No users.")
            return True
        print(f"{'ID':<36}  {'NAME':<20}  CREATED")
        for user in users:
            name = user.name[:17] + "..." if len(user.name) > 20 else user.name
            print(f"{user.id:<36}  {name:<20}  {user.created_at}")
        return True

    if args.cmd == "rotate-key":
        try:
            user, api_key = rotate_key(args.user_id)
        except KeyError:
            print(f"Error: User {args.user_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Key rotated for {user.name}.")
        print(f"  new api_key: {api_key}  ← save this, shown once")
        return True

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
