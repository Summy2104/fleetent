"""Schedule admin CLI commands."""

from __future__ import annotations

import argparse
import sys


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register schedule commands."""
    subparsers.add_parser("list-schedules", help="List all scheduled tasks")

    p_add_sched = subparsers.add_parser("add-schedule", help="Create a new scheduled task")
    p_add_sched.add_argument("--name", required=True, help="Task name")
    p_add_sched.add_argument("--cron", required=True, help="Cron expression (5 fields)")
    p_add_sched.add_argument("--user-id", required=True, help="User UUID to run as")
    p_add_sched.add_argument("--message", required=True, help="Prompt text for the agent")
    p_add_sched.add_argument("--agent-name", default=None, help="Agent name (optional)")
    p_add_sched.add_argument("--timezone", default="UTC", help="Timezone (default: UTC)")

    p_rm_sched = subparsers.add_parser("remove-schedule", help="Remove a scheduled task by id")
    p_rm_sched.add_argument("--task-id", required=True, help="Task UUID")


def handle(args: argparse.Namespace) -> bool:
    """Handle schedule commands."""
    if args.cmd == "list-schedules":
        from fleetent import schedule_store

        tasks = schedule_store.list_tasks()
        if not tasks:
            print("No scheduled tasks")
            return True
        print(f"{'ID':<36}  {'NAME':<20}  {'CRON':<15}  USER_ID")
        for task in tasks:
            print(
                f"{task['id']:<36}  {task['name']:<20}  {task['cron_expr']:<15}  {task['user_id']}"
            )
        return True

    if args.cmd == "add-schedule":
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
        return True

    if args.cmd == "remove-schedule":
        from fleetent import schedule_store

        deleted = schedule_store.delete(args.task_id)
        if not deleted:
            print(f"Error: task {args.task_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Task {args.task_id!r} removed.")
        return True

    return False
