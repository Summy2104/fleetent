"""Shared Memory admin CLI commands."""

from __future__ import annotations

import argparse
import asyncio

from fleetent import observability
from fleetent.platform.admin_cli.common import sanitize_cli_value


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register Shared Memory commands."""
    p_memory = subparsers.add_parser("memory", help="Memory administration")
    memory_sub = p_memory.add_subparsers(dest="memory_cmd", required=True)
    p_shared = memory_sub.add_parser("shared", help="Shared Memory administration")
    shared_sub = p_shared.add_subparsers(dest="shared_cmd", required=True)

    p_list = shared_sub.add_parser("list", help="List Shared Memory by scope")
    _add_scope_args(p_list)
    p_list.add_argument("--include-archived", action="store_true")

    p_create = shared_sub.add_parser("create", help="Create Shared Memory")
    _add_scope_args(p_create)
    p_create.add_argument("--type", required=True)
    p_create.add_argument("--content", required=True)
    p_create.add_argument("--actor", required=True)

    p_update = shared_sub.add_parser("update", help="Update Shared Memory")
    p_update.add_argument("item_id")
    p_update.add_argument("--content")
    p_update.add_argument("--type")
    p_update.add_argument("--status")
    p_update.add_argument("--actor", required=True)

    p_archive = shared_sub.add_parser("archive", help="Archive Shared Memory")
    p_archive.add_argument("item_id")
    p_archive.add_argument("--actor", required=True)


def handle(args: argparse.Namespace) -> bool:
    """Handle Shared Memory commands."""
    if args.cmd != "memory":
        return False
    if args.memory_cmd != "shared":
        return True

    from fleetent.intelligence import memory

    if args.shared_cmd == "list":
        rows = memory.list_shared_memory(
            args.scope_type,
            args.scope_id,
            include_archived=args.include_archived,
        )
        if not rows:
            print("No shared memory items.")
            return True
        print(f"{'ID':<36}  {'SCOPE':<20}  {'TYPE':<10}  {'STATUS':<8}  CONTENT")
        for item in rows:
            scope = f"{item.scope_type}:{item.scope_id}"
            print(
                f"{item.id:<36}  {scope:<20}  {item.type:<10}  "
                f"{item.status:<8}  {sanitize_cli_value(item.content)}"
            )
        return True

    if args.shared_cmd == "create":
        item = asyncio.run(
            memory.create_shared_memory(
                scope_type=args.scope_type,
                scope_id=args.scope_id,
                type=args.type,
                content=args.content,
                created_by=args.actor,
            )
        )
        record_shared_memory_admin_audit("shared_memory.create", item.id, args.actor)
        print(f"shared_memory_id={item.id} status={item.status}")
        return True

    if args.shared_cmd == "update":
        item = asyncio.run(
            memory.update_shared_memory(
                args.item_id,
                content=args.content,
                type=args.type,
                status=args.status,
            )
        )
        record_shared_memory_admin_audit("shared_memory.update", item.id, args.actor)
        print(f"shared_memory_id={item.id} status={item.status}")
        return True

    if args.shared_cmd == "archive":
        item = asyncio.run(memory.archive_shared_memory(args.item_id))
        record_shared_memory_admin_audit("shared_memory.archive", item.id, args.actor)
        print(f"shared_memory_id={item.id} status={item.status}")
        return True

    return True


def _add_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope-type", required=True)
    parser.add_argument("--scope-id", required=True)


def record_shared_memory_admin_audit(action: str, item_id: str, actor: str) -> None:
    """Delegate Shared Memory admin audit recording."""
    try:
        observability.record_trace_event(
            observability.TraceEvent(
                run_id=f"admin:{action}",
                event_type="shared_memory_admin_action",
                payload={"action": action, "item_id": item_id, "actor": actor},
            )
        )
    except Exception:
        return
