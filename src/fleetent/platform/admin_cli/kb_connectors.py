"""Knowledge-base connector admin CLI commands."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from pathlib import Path

from fleetent.config import Settings
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.extraction import (
    run_entity_extraction as _run_entity_extraction,
)
from fleetent.knowledge_base.extraction_store import KnowledgeExtractionRun
from fleetent.platform.admin_cli.common import sanitize_cli_value
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register knowledge-base connector commands."""
    p_kb = subparsers.add_parser("kb", help="Knowledge-base administration")
    kb_sub = p_kb.add_subparsers(dest="kb_cmd", required=True)
    p_extract = kb_sub.add_parser("extract-entities", help="Run explicit KB entity extraction")
    p_extract.add_argument("--tenant-id", default="default")
    p_extract.add_argument("--kb-id", required=True)
    p_extract.add_argument("--document-id")


def handle(args: argparse.Namespace) -> bool:
    """Handle knowledge-base connector commands."""
    if args.cmd != "kb":
        return False
    if args.kb_cmd == "extract-entities":
        _handle_extract_entities(args)
        return True
    return False


async def run_entity_extraction(
    tenant_id: str,
    kb_id: str,
    document_id: str | None = None,
) -> KnowledgeExtractionRun:
    """Delegate entity extraction to the knowledge-base public API."""
    return await _run_entity_extraction(tenant_id, kb_id, document_id=document_id)


def _handle_extract_entities(args: argparse.Namespace) -> None:
    with _use_kb_runtime(args.tenant_id):
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


def _tenant_router() -> TenantRouter:
    data_dir = Path(Settings().database_url.removeprefix("sqlite:///")).parent
    return TenantRouter(SQLiteTenantBackend(data_dir=data_dir))


@contextmanager
def _use_kb_runtime(tenant_id: str):
    from fleetent.knowledge_base import runtime

    scope = _tenant_router().tenant_scope(tenant_id)
    previous_db = runtime._kb_db
    previous_backend = runtime._kb_vector_backend
    runtime.set_database(scope.open_kb_db(KB_MIGRATIONS))
    runtime.set_vector_backend(scope.kb_vector_backend)
    try:
        yield
    finally:
        runtime.set_database(previous_db)
        runtime.set_vector_backend(previous_backend)
