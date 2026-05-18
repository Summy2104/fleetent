"""Admin CLI for user management. Usage: uv run mini-agent-admin <command>"""

import argparse
import sys

from mini_agent.user_store import create_user, list_users, rotate_key


def main() -> None:
    parser = argparse.ArgumentParser(prog="mini-agent-admin", description="User management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-user", help="Create a new user")
    p_create.add_argument("--name", required=True, help="Display name")

    sub.add_parser("list-users", help="List all users")

    p_rotate = sub.add_parser("rotate-key", help="Rotate a user's API key")
    p_rotate.add_argument("--user-id", required=True, help="User UUID")

    args = parser.parse_args()

    if args.cmd == "create-user":
        user = create_user(args.name)
        print("User created.")
        print(f"  id:      {user.id}")
        print(f"  name:    {user.name}")
        print(f"  api_key: {user.api_key}  ← save this, shown once")

    elif args.cmd == "list-users":
        users = list_users()
        if not users:
            print("No users.")
            return
        print(f"{'ID':<38}  {'NAME':<20}  CREATED")
        for u in users:
            print(f"{u.id}  {u.name:<20}  {u.created_at}")

    elif args.cmd == "rotate-key":
        try:
            user = rotate_key(args.user_id)
        except KeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Key rotated for {user.name}.")
        print(f"  new api_key: {user.api_key}  ← save this, shown once")


if __name__ == "__main__":
    main()
