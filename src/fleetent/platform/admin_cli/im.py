"""IM user admin CLI commands."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register IM user commands."""
    subparsers.add_parser("list-pending", help="List unapproved IM users")

    p_approve = subparsers.add_parser("approve-user", help="Approve an IM user")
    p_approve.add_argument("--im-user-id", required=True, type=int, help="im_users.id")

    p_block = subparsers.add_parser(
        "block-user", help="[DEPRECATED] use the admin UI to block IM users"
    )
    p_block.add_argument("--im-user-id", required=True, type=int, help="im_users.id")


def handle(args: argparse.Namespace) -> bool:
    """Handle IM user commands."""
    if args.cmd == "list-pending":
        import fleetent.im_user_store as ius

        pending = ius.list_pending()
        if not pending:
            print("No pending users.")
            return True
        print(f"{'ID':<6}  {'PLATFORM':<12}  {'PLATFORM_USER_ID':<24}  CREATED")
        for row in pending:
            platform_user_id = row["platform_user_id"]
            print(
                f"{row['id']:<6}  {row['platform']:<12}  "
                f"{platform_user_id:<24}  {row['created_at']}"
            )
        return True

    if args.cmd == "approve-user":
        import fleetent.im_user_store as ius
        from fleetent.user_store import _conn as conn_fn

        ius._init_db()
        with conn_fn() as conn:
            row = conn.execute(
                "SELECT id FROM im_users WHERE id = ?", (args.im_user_id,)
            ).fetchone()
        if not row:
            print(f"Error: IM user {args.im_user_id} not found.", file=sys.stderr)
            sys.exit(1)
        ius.approve_user(args.im_user_id)
        print(f"IM user {args.im_user_id} approved.")
        return True

    if args.cmd == "block-user":
        print(
            "block-user is deprecated; block/restore IM users from the admin UI/API instead.",
            file=sys.stderr,
        )
        return True

    return False
