"""Admin CLI for user management. Usage: uv run fleetent-admin <command>"""

import argparse
import asyncio
import sys
from collections.abc import Mapping
from pathlib import Path

import yaml

from fleetent.user_store import create_user, list_users, rotate_key

_SETTINGS_YAML = Path("config/settings.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(prog="fleetent-admin", description="User management CLI")
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

    p_block = sub.add_parser("block-user", help="[DEPRECATED] use the admin UI to block IM users")
    p_block.add_argument("--im-user-id", required=True, type=int, help="im_users.id")

    sub.add_parser("seed-builtin-admin", help="Seed the built-in admin (first run)")

    # --- channel agent commands ---
    p_assign_ch = sub.add_parser("assign-channel", help="Bind an agent to a channel")
    p_assign_ch.add_argument("--platform", required=True)
    p_assign_ch.add_argument("--channel-id", required=True)
    p_assign_ch.add_argument("--agent-name", required=True)

    p_unassign_ch = sub.add_parser("unassign-channel", help="Remove channel-agent binding")
    p_unassign_ch.add_argument("--platform", required=True)
    p_unassign_ch.add_argument("--channel-id", required=True)

    # --- schedule commands ---
    sub.add_parser("list-schedules", help="List all scheduled tasks")

    p_add_sched = sub.add_parser("add-schedule", help="Create a new scheduled task")
    p_add_sched.add_argument("--name", required=True, help="Task name")
    p_add_sched.add_argument("--cron", required=True, help="Cron expression (5 fields)")
    p_add_sched.add_argument("--user-id", required=True, help="User UUID to run as")
    p_add_sched.add_argument("--message", required=True, help="Prompt text for the agent")
    p_add_sched.add_argument("--agent-name", default=None, help="Agent name (optional)")
    p_add_sched.add_argument("--timezone", default="UTC", help="Timezone (default: UTC)")

    p_rm_sched = sub.add_parser("remove-schedule", help="Remove a scheduled task by id")
    p_rm_sched.add_argument("--task-id", required=True, help="Task UUID")

    # --- default agent command ---
    p_default = sub.add_parser("set-default-agent", help="Set or clear the default agent")
    p_default_group = p_default.add_mutually_exclusive_group(required=True)
    p_default_group.add_argument("--agent-name", help="Agent name to set as default")
    p_default_group.add_argument("--clear", action="store_true", help="Clear default agent")

    # --- knowledge-base connector operations ---
    p_kb = sub.add_parser("kb", help="Knowledge-base administration")
    kb_sub = p_kb.add_subparsers(dest="kb_cmd", required=True)
    p_kb_connectors = kb_sub.add_parser("connectors", help="Knowledge-base connectors")
    kb_connectors_sub = p_kb_connectors.add_subparsers(dest="connector_cmd", required=True)
    kb_connectors_sub.add_parser("list", help="List configured connectors")
    p_connector_check = kb_connectors_sub.add_parser("check", help="Check connector health")
    p_connector_check.add_argument("connector_id")
    p_connector_status = kb_connectors_sub.add_parser("status", help="Show connector status")
    p_connector_status.add_argument("connector_id")
    p_connector_sync = kb_connectors_sub.add_parser("sync", help="Run connector sync")
    p_connector_sync.add_argument("connector_id")
    p_connector_sync.add_argument("--dry-run", action="store_true")

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
        import fleetent.im_user_store as ius

        pending = ius.list_pending()
        if not pending:
            print("No pending users.")
            return
        print(f"{'ID':<6}  {'PLATFORM':<12}  {'PLATFORM_USER_ID':<24}  CREATED")
        for row in pending:
            pid = row["platform_user_id"]
            print(f"{row['id']:<6}  {row['platform']:<12}  {pid:<24}  {row['created_at']}")

    elif args.cmd == "approve-user":
        import fleetent.im_user_store as ius

        ius._init_db()
        from fleetent.user_store import _conn as conn_fn

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
        # Deprecated (v1.0): blocking IM users moved to the admin UI/API. This command
        # no longer changes state; it only prints a deprecation notice.
        print(
            "block-user is deprecated; block/restore IM users from the admin UI/API instead.",
            file=sys.stderr,
        )

    elif args.cmd == "seed-builtin-admin":
        from fleetent.auth import seed_builtin_admin

        result = seed_builtin_admin()
        if result is None:
            print("Built-in admin already exists.")
        else:
            admin_user, temp_password = result
            print("Built-in admin created.")
            print(f"  username:         {admin_user.name}")
            print(f"  initial_password: {temp_password}  ← change on first login, shown once")

    elif args.cmd == "assign-channel":
        from fleetent.agent_store import assign_channel, get_by_name

        agent = get_by_name(args.agent_name)
        if agent is None:
            print(f"Error: Agent {args.agent_name!r} not found.", file=sys.stderr)
            sys.exit(1)
        assign_channel(args.platform, args.channel_id, agent.id)
        print(f"Channel {args.platform}/{args.channel_id} → agent '{args.agent_name}'.")

    elif args.cmd == "unassign-channel":
        from fleetent.agent_store import unassign_channel

        unassign_channel(args.platform, args.channel_id)
        print(f"Channel {args.platform}/{args.channel_id} unassigned.")

    elif args.cmd == "list-schedules":
        from fleetent import schedule_store

        tasks = schedule_store.list_tasks()
        if not tasks:
            print("No scheduled tasks")
            return
        print(f"{'ID':<36}  {'NAME':<20}  {'CRON':<15}  USER_ID")
        for t in tasks:
            print(f"{t['id']:<36}  {t['name']:<20}  {t['cron_expr']:<15}  {t['user_id']}")

    elif args.cmd == "add-schedule":
        from fleetent import schedule_store

        task = schedule_store.create(
            name=args.name,
            cron_expr=args.cron,
            timezone=args.timezone,
            user_id=args.user_id,
            agent_name=args.agent_name,
            message=args.message,
            source="dynamic",
        )
        print(task["id"])

    elif args.cmd == "remove-schedule":
        from fleetent import schedule_store

        deleted = schedule_store.delete(args.task_id)
        if not deleted:
            print(f"Error: task {args.task_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Task {args.task_id!r} removed.")

    elif args.cmd == "set-default-agent":
        _set_default_agent(args)

    elif args.cmd == "kb":
        _handle_kb(args)


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


def _handle_kb(args: argparse.Namespace) -> None:
    if args.kb_cmd == "connectors":
        _handle_kb_connectors(args)


def _handle_kb_connectors(args: argparse.Namespace) -> None:
    from fleetent.intelligence.knowledge_base import operations

    if args.connector_cmd == "list":
        connectors = operations.list_configured_connectors()
        if not connectors:
            print("No connectors configured.")
            return
        print(f"{'ID':<24}  {'TYPE':<14}  {'ENABLED':<7}  {'TENANT':<12}  {'KB':<16}  SCOPE")
        for item in connectors:
            print(
                f"{item.connector_id:<24}  {item.connector_type:<14}  "
                f"{str(item.enabled):<7}  {item.tenant_id:<12}  {item.kb_id:<16}  {item.scope}"
            )
        return

    if args.connector_cmd == "check":
        check_result = asyncio.run(operations.check_connector(args.connector_id))
        print(f"connector_id={check_result.connector_id}")
        print(f"status={check_result.status}")
        print(f"message={_sanitize_cli_value(check_result.message)}")
        return

    if args.connector_cmd == "status":
        status = operations.get_connector_status(args.connector_id)
        print(f"connector_id={status.connector_id}")
        print(f"status={status.last_status}")
        if status.last_summary:
            print(_summary_line(status.last_summary))
        if status.last_error:
            print(f"error={_sanitize_cli_value(status.last_error)}")
        return

    if args.connector_cmd == "sync":
        sync_result = asyncio.run(
            operations.run_connector_sync(args.connector_id, dry_run=args.dry_run)
        )
        print(f"connector_id={sync_result.connector_id}")
        print(f"status={sync_result.status}")
        if sync_result.summary:
            print(_summary_line(sync_result.summary))
        if sync_result.error:
            print(f"error={_sanitize_cli_value(sync_result.error)}")


def _summary_line(summary: Mapping[str, object]) -> str:
    return " ".join(f"{key}={_sanitize_cli_value(value)}" for key, value in sorted(summary.items()))


def _sanitize_cli_value(value: object) -> str:
    from fleetent.intelligence.knowledge_base import operations
    from fleetent.observability.structured_logging import _redact_value

    return operations._sanitize_text(str(_redact_value(value)))


if __name__ == "__main__":
    main()
