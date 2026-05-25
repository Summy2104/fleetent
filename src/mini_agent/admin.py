"""Admin CLI for user management. Usage: uv run mini-agent-admin <command>"""

import argparse
import sys
from pathlib import Path

import yaml

from mini_agent.user_store import create_user, list_users, rotate_key

_SETTINGS_YAML = Path("config/settings.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mini-agent-admin", description="User management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # --- existing user commands ---
    p_create = sub.add_parser("create-user", help="Create a new user")
    p_create.add_argument("--name", required=True, help="Display name")

    sub.add_parser("list-users", help="List all users")

    p_rotate = sub.add_parser("rotate-key", help="Rotate a user's API key")
    p_rotate.add_argument("--user-id", required=True, help="User UUID")

    # --- allowlist commands ---
    sub.add_parser("list-pending", help="List unapproved IM users")

    p_approve = sub.add_parser("approve-user", help="Approve an IM user")
    p_approve.add_argument("--im-user-id", required=True, type=int, help="im_users.id")

    p_block = sub.add_parser("block-user", help="Block/revoke an IM user")
    p_block.add_argument("--im-user-id", required=True, type=int, help="im_users.id")

    # --- channel agent commands ---
    p_assign_ch = sub.add_parser("assign-channel", help="Bind an agent to a channel")
    p_assign_ch.add_argument("--platform", required=True)
    p_assign_ch.add_argument("--channel-id", required=True)
    p_assign_ch.add_argument("--agent-name", required=True)

    p_unassign_ch = sub.add_parser("unassign-channel", help="Remove channel-agent binding")
    p_unassign_ch.add_argument("--platform", required=True)
    p_unassign_ch.add_argument("--channel-id", required=True)

    # --- default agent command ---
    p_default = sub.add_parser("set-default-agent", help="Set or clear the default agent")
    p_default_group = p_default.add_mutually_exclusive_group(required=True)
    p_default_group.add_argument("--agent-name", help="Agent name to set as default")
    p_default_group.add_argument("--clear", action="store_true", help="Clear default agent")

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
        print(f"{'ID':<36}  {'NAME':<20}  CREATED")
        for u in users:
            name = u.name[:17] + "..." if len(u.name) > 20 else u.name
            print(f"{u.id:<36}  {name:<20}  {u.created_at}")

    elif args.cmd == "rotate-key":
        try:
            user = rotate_key(args.user_id)
        except KeyError:
            print(f"Error: User {args.user_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Key rotated for {user.name}.")
        print(f"  new api_key: {user.api_key}  ← save this, shown once")

    elif args.cmd == "list-pending":
        import mini_agent.im_user_store as ius
        pending = ius.list_pending()
        if not pending:
            print("No pending users.")
            return
        print(f"{'ID':<6}  {'PLATFORM':<12}  {'PLATFORM_USER_ID':<24}  CREATED")
        for row in pending:
            pid = row["platform_user_id"]
            print(f"{row['id']:<6}  {row['platform']:<12}  {pid:<24}  {row['created_at']}")

    elif args.cmd == "approve-user":
        import mini_agent.im_user_store as ius
        ius._init_db()
        from mini_agent.user_store import _conn as conn_fn
        with conn_fn() as conn:
            row = conn.execute(
                "SELECT id FROM im_users WHERE id = ?", (args.im_user_id,)
            ).fetchone()
        if not row:
            print(f"Error: IM user {args.im_user_id} not found.", file=sys.stderr)
            sys.exit(1)
        ius.approve_user(args.im_user_id)
        print(f"IM user {args.im_user_id} approved.")

    elif args.cmd == "block-user":
        import mini_agent.im_user_store as ius
        ius._init_db()
        from mini_agent.user_store import _conn as conn_fn
        with conn_fn() as conn:
            row = conn.execute(
                "SELECT id FROM im_users WHERE id = ?", (args.im_user_id,)
            ).fetchone()
        if not row:
            print(f"Error: IM user {args.im_user_id} not found.", file=sys.stderr)
            sys.exit(1)
        ius.block_user(args.im_user_id)
        print(f"IM user {args.im_user_id} blocked.")

    elif args.cmd == "assign-channel":
        from mini_agent.agent_store import assign_channel, get_by_name
        agent = get_by_name(args.agent_name)
        if agent is None:
            print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
            sys.exit(1)
        assign_channel(args.platform, args.channel_id, agent.id)
        print(f"Channel {args.platform}/{args.channel_id} → agent '{args.agent_name}'.")

    elif args.cmd == "unassign-channel":
        from mini_agent.agent_store import unassign_channel
        unassign_channel(args.platform, args.channel_id)
        print(f"Channel {args.platform}/{args.channel_id} unassigned.")

    elif args.cmd == "set-default-agent":
        _set_default_agent(args)


def _set_default_agent(args: argparse.Namespace) -> None:
    data: dict[str, object] = {}
    if _SETTINGS_YAML.exists():
        data = yaml.safe_load(_SETTINGS_YAML.read_text()) or {}

    if args.clear:
        data.pop("default_agent_name", None)
        print("Default agent cleared.")
    else:
        data["default_agent_name"] = args.agent_name
        print(f"Default agent set to '{args.agent_name}'.")

    _SETTINGS_YAML.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_YAML.write_text(yaml.safe_dump(data))


if __name__ == "__main__":
    main()
