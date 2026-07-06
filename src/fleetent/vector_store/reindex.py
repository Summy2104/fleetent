import asyncio
import importlib
import inspect
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Protocol, cast

from fleetent.vector_store import namespaces, runtime

_knowledge_base: ModuleType | None = None
_memory: ModuleType | None = None


def _memory_module() -> ModuleType:
    return _memory_module_impl()


def _memory_module_impl() -> ModuleType:
    return importlib.import_module("fleetent.memory")


def _knowledge_base_module() -> ModuleType:
    return _knowledge_base_module_impl()


def _knowledge_base_module_impl() -> ModuleType:
    return importlib.import_module("fleetent.knowledge_base")


def _set_imported_modules(
    memory_module: ModuleType | None = None, kb_module: ModuleType | None = None
) -> None:
    global memory, knowledge_base, _memory, _knowledge_base
    if memory_module is not None:
        memory = memory_module
        _memory = memory_module
    if kb_module is not None:
        knowledge_base = kb_module
        _knowledge_base = kb_module


memory: ModuleType | None = _memory_module()
knowledge_base: ModuleType | None = _knowledge_base_module()

_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_PACING_SECONDS = 0.2


class _VectorBackendLike(Protocol):
    async def upsert(self, item_id: str, vector: list[float], namespace: str) -> None: ...

    async def clear_namespace(self, namespace: str) -> None: ...


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
    scope_type: str | None = None
    scope_id: str | None = None
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
    if request.owner not in {"memory", "knowledge_base", "agent_memory"}:
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
    if request.owner == "agent_memory":
        return namespaces.agent_memory_namespace()
    return namespaces.knowledge_namespace(request.tenant_id, request.kb_id or "")


def _items_for_request(request: ReindexRequest) -> list[IndexableItem]:
    if request.owner == "memory":
        module = memory if memory is not None else _memory_module()
        return list(module.iter_indexable_memories(request.user_id or ""))
    if request.owner == "agent_memory":
        module = memory if memory is not None else _memory_module()
        return list(module.iter_indexable_agent_memories())
    module = knowledge_base if knowledge_base is not None else _knowledge_base_module()
    return list(module.iter_indexable_knowledge_chunks(request.tenant_id, request.kb_id or ""))


def _rebuild(request: ReindexRequest, namespace: str, items: list[IndexableItem]) -> ReindexSummary:
    _clear_namespace(request, namespace)
    reindexed = 0
    failed = 0
    for item in items:
        if _upsert_with_retry(request, item):
            reindexed += 1
        else:
            failed += 1
        _sleep(_PACING_SECONDS)
    return ReindexSummary(
        owner=request.owner,
        namespace=namespace,
        dry_run=False,
        scanned=len(items),
        reindexed=reindexed,
        skipped=0,
        failed=failed,
    )


def _clear_namespace(request: ReindexRequest, namespace: str) -> None:
    backend = _injected_backend(request)
    if backend is None:
        _run_sync(runtime.clear_namespace(namespace))
        return
    _run_sync(backend.clear_namespace(namespace))


def _upsert_with_retry(request: ReindexRequest, item: IndexableItem) -> bool:
    for attempt in range(len(_BACKOFF_SECONDS) + 1):
        try:
            _upsert_item(request, item)
            return True
        except Exception:
            if attempt == len(_BACKOFF_SECONDS):
                return False
            _sleep(_BACKOFF_SECONDS[attempt])
    return False


def _upsert_item(request: ReindexRequest, item: IndexableItem) -> None:
    backend = _injected_backend(request)
    if backend is None:
        _run_sync(runtime.upsert(item.id, item.content, item.namespace))
        return
    vector = asyncio.run(_embed_for_reindex(item.content))
    _run_sync(backend.upsert(item.id, vector, item.namespace))


def _injected_backend(request: ReindexRequest) -> _VectorBackendLike | None:
    if request.owner != "knowledge_base":
        return None
    module = knowledge_base if knowledge_base is not None else _knowledge_base_module()
    runtime_module = getattr(module, "runtime", None)
    if runtime_module is None:
        return None
    try:
        return cast(_VectorBackendLike, runtime_module._vector_backend())
    except RuntimeError:
        return None


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _run_sync(result: object) -> None:
    if inspect.isawaitable(result):
        asyncio.run(_await_result(result))


async def _await_result(result: Awaitable[object]) -> None:
    await result


async def _embed_for_reindex(content: str) -> list[float]:
    return await runtime.embed_text(content)
