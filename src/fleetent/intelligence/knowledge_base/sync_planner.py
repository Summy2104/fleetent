import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fleetent.intelligence.knowledge_base import runtime
from fleetent.intelligence.knowledge_base.connectors.base import DocumentRef
from fleetent.intelligence.knowledge_base.connectors.local import LocalDirectoryDataSource
from fleetent.intelligence.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.intelligence.knowledge_base.connectors.sync import LocalDirectorySourceConfig
from fleetent.intelligence.knowledge_base.parsers import (
    ParsedDocument,
    parse_html,
    parse_markdown,
    parse_text,
)


class SyncAction(StrEnum):
    """Action names emitted by sync planners and consumed by executors."""

    INGEST_NEW = "ingest_new"
    REINGEST_CHANGED = "reingest_changed"
    SKIP_UNCHANGED = "skip_unchanged"
    DELETE_MISSING = "delete_missing"


@dataclass(frozen=True)
class SyncPlanSummary:
    """Counts describing a generated sync plan."""

    scanned: int
    planned: int
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    unsupported: int = 0
    unchanged: int = 0
    deleted: int = 0


@dataclass(frozen=True)
class SyncExecutionSummary:
    """Counts returned after applying a sync plan."""

    scanned: int
    ingested: int
    skipped: int
    failed: int
    unsupported: int = 0
    unchanged: int = 0
    deleted: int = 0


@dataclass(frozen=True)
class SyncPlanItem:
    """One deterministic sync operation for a source document."""

    action: SyncAction
    source_id: str
    tenant_id: str
    kb_id: str
    source_path: str
    filename: str
    document_format: str
    mtime_ns: int | None = None
    content_hash: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class SyncPlan:
    """A deterministic sync plan plus source/config context needed for execution."""

    source_config: LocalDirectorySourceConfig
    tenant_id: str
    kb_id: str
    items: list[SyncPlanItem]
    summary: SyncPlanSummary


async def plan_local_directory_sync(
    config: LocalDirectorySourceConfig,
    tenant_id: str,
    kb_id: str,
) -> SyncPlan:
    """Plan a local directory sync without mutating knowledge-base state."""

    source = LocalDirectoryDataSource(
        root_path=config.root_path,
        allowed_roots=config.allowed_roots,
    )
    refs = source.list_documents()
    unsupported = source.count_unsupported_documents()
    state_store = LocalSourceStateStore(runtime._database())
    existing_states = {
        state.source_path: state
        for state in state_store.list_for_source(
            source_id=config.source_id,
            tenant_id=tenant_id,
            kb_id=kb_id,
        )
    }
    seen_paths: set[str] = set()
    items: list[SyncPlanItem] = []

    for ref in refs:
        content = source.fetch(ref)
        if ref.path is None:
            raise ValueError("local document ref must include path")
        source_path = ref.path
        seen_paths.add(source_path)
        stat = Path(source_path).stat()
        content_hash = hashlib.sha256(content).hexdigest()
        state = existing_states.get(source_path)
        action = _action_for_state(state, stat.st_mtime_ns, content_hash)
        items.append(
            SyncPlanItem(
                action=action,
                source_id=config.source_id,
                tenant_id=tenant_id,
                kb_id=kb_id,
                source_path=source_path,
                filename=ref.filename,
                document_format=ref.format,
                mtime_ns=stat.st_mtime_ns,
                content_hash=content_hash,
                document_id=state.document_id if state is not None else None,
            )
        )

    for state in existing_states.values():
        if state.source_path in seen_paths:
            continue
        items.append(
            SyncPlanItem(
                action=SyncAction.DELETE_MISSING,
                source_id=state.source_id,
                tenant_id=state.tenant_id,
                kb_id=state.kb_id,
                source_path=state.source_path,
                filename=Path(state.source_path).name,
                document_format="",
                document_id=state.document_id,
                mtime_ns=state.mtime_ns,
                content_hash=state.content_hash,
            )
        )

    return SyncPlan(
        source_config=config,
        tenant_id=tenant_id,
        kb_id=kb_id,
        items=items,
        summary=SyncPlanSummary(
            scanned=len(refs) + unsupported,
            planned=len(items),
            ingested=sum(1 for item in items if item.action is SyncAction.INGEST_NEW),
            skipped=sum(1 for item in items if item.action is SyncAction.SKIP_UNCHANGED),
            unsupported=unsupported,
            unchanged=sum(1 for item in items if item.action is SyncAction.SKIP_UNCHANGED),
            deleted=sum(1 for item in items if item.action is SyncAction.DELETE_MISSING),
        ),
    )


async def execute_sync_plan(plan: SyncPlan) -> SyncExecutionSummary:
    """Apply sync plan items, isolating failures to the current item."""

    state_store = LocalSourceStateStore(runtime._database())
    source = LocalDirectoryDataSource(
        root_path=plan.source_config.root_path,
        allowed_roots=plan.source_config.allowed_roots,
    )
    ingested = 0
    skipped = plan.summary.unsupported
    failed = 0
    unchanged = 0
    deleted = 0

    for item in plan.items:
        try:
            if item.action is SyncAction.SKIP_UNCHANGED:
                skipped += 1
                unchanged += 1
                continue
            if item.action is SyncAction.DELETE_MISSING:
                if item.document_id is None:
                    raise ValueError("delete_missing plan item requires document_id")
                await runtime.delete(item.document_id)
                state_store.delete(item.source_id, item.tenant_id, item.kb_id, item.source_path)
                deleted += 1
                continue
            if item.action is SyncAction.REINGEST_CHANGED:
                if item.document_id is None:
                    raise ValueError("reingest_changed plan item requires document_id")
                await runtime.delete(item.document_id)
            if item.action not in {SyncAction.INGEST_NEW, SyncAction.REINGEST_CHANGED}:
                raise ValueError(f"unsupported sync action: {item.action}")

            parsed = _parse_item(source, item)
            document = await runtime.ingest_parsed(
                parsed,
                tenant_id=item.tenant_id,
                kb_id=item.kb_id,
                source=f"local:{item.source_id}",
                source_url=item.source_path,
            )
            if item.mtime_ns is None or item.content_hash is None:
                raise ValueError("ingest plan item requires mtime_ns and content_hash")
            state_store.upsert(
                LocalSourceState(
                    source_id=item.source_id,
                    tenant_id=item.tenant_id,
                    kb_id=item.kb_id,
                    source_path=item.source_path,
                    mtime_ns=item.mtime_ns,
                    content_hash=item.content_hash,
                    document_id=document.id,
                )
            )
            ingested += 1
        except Exception:
            failed += 1

    return SyncExecutionSummary(
        scanned=plan.summary.scanned,
        ingested=ingested,
        skipped=skipped,
        failed=failed,
        unsupported=plan.summary.unsupported,
        unchanged=unchanged,
        deleted=deleted,
    )


def _action_for_state(
    state: LocalSourceState | None,
    mtime_ns: int,
    content_hash: str,
) -> SyncAction:
    if state is None:
        return SyncAction.INGEST_NEW
    if state.mtime_ns == mtime_ns and state.content_hash == content_hash:
        return SyncAction.SKIP_UNCHANGED
    return SyncAction.REINGEST_CHANGED


def _parse_item(source: LocalDirectoryDataSource, item: SyncPlanItem) -> ParsedDocument:
    content = source.fetch(
        DocumentRef(
            id=f"local:{item.source_path}",
            filename=item.filename,
            format=item.document_format,
            path=item.source_path,
            metadata={"source_path": item.source_path},
        )
    )
    text = content.decode("utf-8")
    if item.document_format == "text":
        return parse_text(item.filename, text)
    if item.document_format == "markdown":
        return parse_markdown(item.filename, text)
    if item.document_format == "html":
        return parse_html(item.filename, text)
    raise ValueError(f"unsupported local document format: {item.document_format}")
