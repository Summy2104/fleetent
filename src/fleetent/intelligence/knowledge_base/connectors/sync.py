import hashlib
from dataclasses import dataclass
from pathlib import Path

from fleetent.intelligence.knowledge_base import runtime
from fleetent.intelligence.knowledge_base.connectors.local import LocalDirectoryDataSource
from fleetent.intelligence.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    parse_html,
    parse_markdown,
    parse_text,
)


@dataclass(frozen=True)
class LocalDirectorySourceConfig:
    """Configuration for a manual local directory sync."""

    source_id: str
    root_path: str | Path
    allowed_roots: list[str | Path]


@dataclass(frozen=True)
class LocalSyncSummary:
    """Counts returned by a manual local directory sync."""

    scanned: int
    ingested: int
    skipped: int
    failed: int
    unsupported: int = 0
    unchanged: int = 0


async def sync_local_directory(
    config: LocalDirectorySourceConfig,
    tenant_id: str,
    kb_id: str,
) -> LocalSyncSummary:
    """Manually import supported files from an allowlisted local directory."""

    source = LocalDirectoryDataSource(
        root_path=config.root_path,
        allowed_roots=config.allowed_roots,
    )
    refs = source.list_documents()
    unsupported = source.count_unsupported_documents()
    scanned = len(refs) + unsupported
    ingested = 0
    skipped = unsupported
    failed = 0
    unchanged = 0
    state_store = LocalSourceStateStore(runtime._database())

    for ref in refs:
        try:
            content = source.fetch(ref)
            if ref.path is None:
                raise ValueError("local document ref must include path")
            source_path = ref.path
            stat = Path(source_path).stat()
            content_hash = hashlib.sha256(content).hexdigest()
            if state_store.is_unchanged(
                source_id=config.source_id,
                tenant_id=tenant_id,
                kb_id=kb_id,
                source_path=source_path,
                mtime_ns=stat.st_mtime_ns,
                content_hash=content_hash,
            ):
                skipped += 1
                unchanged += 1
                continue

            parsed = _parse_ref(ref.filename, ref.format, content)
            document = await runtime.ingest_parsed(
                parsed,
                tenant_id=tenant_id,
                kb_id=kb_id,
                source=f"local:{config.source_id}",
                source_url=source_path,
            )
            state_store.upsert(
                LocalSourceState(
                    source_id=config.source_id,
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    source_path=source_path,
                    mtime_ns=stat.st_mtime_ns,
                    content_hash=content_hash,
                    document_id=document.id,
                )
            )
            ingested += 1
        except Exception:
            failed += 1

    return LocalSyncSummary(
        scanned=scanned,
        ingested=ingested,
        skipped=skipped,
        failed=failed,
        unsupported=unsupported,
        unchanged=unchanged,
    )


def _parse_ref(filename: str, document_format: str, content: bytes) -> ParsedDocument:
    text = content.decode("utf-8")
    if document_format == "text":
        return parse_text(filename, text)
    if document_format == "markdown":
        return parse_markdown(filename, text)
    if document_format == "html":
        return parse_html(filename, text)
    raise ValueError(f"unsupported local document format: {document_format}")
