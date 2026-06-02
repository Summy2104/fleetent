"""Knowledge-base connector admin CLI commands."""

from __future__ import annotations

import argparse
import asyncio

from fleetent.platform.admin_cli.common import sanitize_cli_value, summary_line


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register knowledge-base connector commands."""
    p_kb = subparsers.add_parser("kb", help="Knowledge-base administration")
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


def handle(args: argparse.Namespace) -> bool:
    """Handle knowledge-base connector commands."""
    if args.cmd != "kb":
        return False
    if args.kb_cmd == "connectors":
        _handle_connectors(args)
    return True


def _handle_connectors(args: argparse.Namespace) -> None:
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
        print(f"message={sanitize_cli_value(check_result.message)}")
        return

    if args.connector_cmd == "status":
        status = operations.get_connector_status(args.connector_id)
        print(f"connector_id={status.connector_id}")
        print(f"status={status.last_status}")
        if status.last_summary:
            print(summary_line(status.last_summary))
        if status.last_error:
            print(f"error={sanitize_cli_value(status.last_error)}")
        return

    if args.connector_cmd == "sync":
        sync_result = asyncio.run(
            operations.run_connector_sync(args.connector_id, dry_run=args.dry_run)
        )
        print(f"connector_id={sync_result.connector_id}")
        print(f"status={sync_result.status}")
        if sync_result.summary:
            print(summary_line(sync_result.summary))
        if sync_result.error:
            print(f"error={sanitize_cli_value(sync_result.error)}")
