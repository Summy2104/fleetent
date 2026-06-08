"""Knowledge-base connector admin CLI commands."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from fleetent.knowledge_base.extraction import (
    run_entity_extraction as _run_entity_extraction,
)
from fleetent.knowledge_base.extraction_store import KnowledgeExtractionRun
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
    p_connector_sync.add_argument("--yes", action="store_true")
    p_connector_sync.add_argument("--pilot-fixture", action="store_true")
    p_extract = kb_sub.add_parser("extract-entities", help="Run explicit KB entity extraction")
    p_extract.add_argument("--tenant-id", default="default")
    p_extract.add_argument("--kb-id", required=True)
    p_extract.add_argument("--document-id")


def handle(args: argparse.Namespace) -> bool:
    """Handle knowledge-base connector commands."""
    if args.cmd != "kb":
        return False
    if args.kb_cmd == "connectors":
        _handle_connectors(args)
        return True
    if args.kb_cmd == "extract-entities":
        _handle_extract_entities(args)
    return True


async def run_entity_extraction(
    tenant_id: str,
    kb_id: str,
    document_id: str | None = None,
) -> KnowledgeExtractionRun:
    """Delegate entity extraction to the knowledge-base public API."""
    return await _run_entity_extraction(tenant_id, kb_id, document_id=document_id)


def _handle_connectors(args: argparse.Namespace) -> None:
    from fleetent.knowledge_base import operations

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
        if not args.dry_run and not _execute_sync_allowed(operations, args):
            sys.exit(1)
        sync_result = asyncio.run(
            operations.run_connector_sync(args.connector_id, dry_run=args.dry_run)
        )
        print(f"connector_id={sync_result.connector_id}")
        print(f"status={sync_result.status}")
        if sync_result.summary:
            print(summary_line(sync_result.summary))
        if sync_result.error:
            print(f"error={sanitize_cli_value(sync_result.error)}")


def _execute_sync_allowed(operations: Any, args: argparse.Namespace) -> bool:
    if not args.yes:
        print(
            "connector execute sync requires --yes; run dry-run first: "
            f"fleetent-admin kb connectors sync {args.connector_id} --dry-run",
            file=sys.stderr,
        )
        return False
    if not args.pilot_fixture:
        print("connector execute sync requires --pilot-fixture", file=sys.stderr)
        return False
    definition = operations.get_connector_config(args.connector_id)
    env_flag = _execute_sync_env_flag(str(definition.connector_type))
    if os.getenv(env_flag) != "1":
        print(f"connector execute sync requires {env_flag}=1", file=sys.stderr)
        return False
    return True


def _execute_sync_env_flag(connector_type: str) -> str:
    if connector_type == "confluence":
        return "FLEETENT_CONFLUENCE_EXECUTE_SYNC"
    return "FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC"


def _handle_extract_entities(args: argparse.Namespace) -> None:
    summary = asyncio.run(
        run_entity_extraction(
            args.tenant_id,
            args.kb_id,
            document_id=args.document_id,
        )
    )
    print(f"status={sanitize_cli_value(summary.status)}")
    print(f"tenant_id={sanitize_cli_value(summary.tenant_id)}")
    print(f"kb_id={sanitize_cli_value(summary.kb_id)}")
    if summary.document_id:
        print(f"document_id={sanitize_cli_value(summary.document_id)}")
    print(f"documents_scanned={summary.documents_scanned}")
    print(f"chunks_scanned={summary.chunks_scanned}")
    print(f"entities_upserted={summary.entities_upserted}")
    print(f"mentions_written={summary.mentions_written}")
    print(f"relations_written={summary.relations_written}")
    print(f"failed_count={summary.failed_count}")
    if summary.error_summary:
        print(f"error={sanitize_cli_value(summary.error_summary)}")
