import asyncio
import inspect
from collections.abc import Awaitable
from dataclasses import dataclass, field

from fleetent import memory_layer
from fleetent.intelligence import knowledge_base
from fleetent.intelligence.vector_store import namespaces, runtime


@dataclass(frozen=True)
class IndexableItem:
    """Source record that can be written to vector_store."""

    id: str
    content: str
    namespace: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReindexRequest:
    """Synchronous vector reindex request."""

    owner: str
    mode: str = "rebuild"
    user_id: str | None = None
    tenant_id: str = "default"
    kb_id: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class ReindexSummary:
    """Counts returned by a synchronous reindex operation."""

    owner: str
    namespace: str
    dry_run: bool
    scanned: int
    reindexed: int
    skipped: int
    failed: int


def reindex(request: ReindexRequest) -> ReindexSummary:
    """Synchronously rebuild or dry-run a vector namespace from source records."""
    _validate_request(request)
    namespace = _namespace_for_request(request)
    items = list(_items_for_request(request))
    if request.dry_run:
        return ReindexSummary(
            owner=request.owner,
            namespace=namespace,
            dry_run=True,
            scanned=len(items),
            reindexed=0,
            skipped=len(items),
            failed=0,
        )

    return _rebuild(request, namespace, items)


def _validate_request(request: ReindexRequest) -> None:
    if request.owner not in {"memory", "knowledge_base"}:
        raise ValueError(f"unsupported reindex owner: {request.owner}")
    if request.mode != "rebuild":
        raise ValueError(f"unsupported reindex mode: {request.mode}")
    if request.owner == "memory" and not (request.user_id and request.user_id.strip()):
        raise ValueError("user_id is required for memory reindex")
    if request.owner == "knowledge_base" and not (request.kb_id and request.kb_id.strip()):
        raise ValueError("kb_id is required for knowledge_base reindex")


def _namespace_for_request(request: ReindexRequest) -> str:
    if request.owner == "memory":
        return namespaces.memory_namespace(request.user_id or "")
    return namespaces.knowledge_namespace(request.tenant_id, request.kb_id or "")


def _items_for_request(request: ReindexRequest) -> list[IndexableItem]:
    if request.owner == "memory":
        return list(memory_layer.iter_indexable_memories(request.user_id or ""))
    return list(
        knowledge_base.iter_indexable_knowledge_chunks(request.tenant_id, request.kb_id or "")
    )


def _rebuild(request: ReindexRequest, namespace: str, items: list[IndexableItem]) -> ReindexSummary:
    _run_sync(runtime.clear_namespace(namespace))
    reindexed = 0
    failed = 0
    for item in items:
        try:
            _run_sync(runtime.upsert(item.id, item.content, item.namespace))
        except Exception:
            failed += 1
            continue
        reindexed += 1
    return ReindexSummary(
        owner=request.owner,
        namespace=namespace,
        dry_run=False,
        scanned=len(items),
        reindexed=reindexed,
        skipped=0,
        failed=failed,
    )


def _run_sync(result: object) -> None:
    if inspect.isawaitable(result):
        asyncio.run(_await_result(result))


async def _await_result(result: Awaitable[object]) -> None:
    await result
