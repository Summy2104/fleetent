import importlib
from dataclasses import fields

import pytest


def test_reindex_public_api_shape_is_importable():
    from fleetent.vector_store import (
        ReindexRequest,
        ReindexSummary,
        reindex,
    )

    summary = ReindexSummary(
        owner="memory",
        namespace="mem:alice",
        dry_run=True,
        scanned=1,
        reindexed=0,
        skipped=1,
        failed=0,
    )

    assert callable(reindex)
    assert ReindexRequest(owner="memory", user_id="alice").owner == "memory"
    assert [field.name for field in fields(ReindexSummary)] == [
        "owner",
        "namespace",
        "dry_run",
        "scanned",
        "reindexed",
        "skipped",
        "failed",
    ]
    assert summary.scanned == 1


@pytest.mark.parametrize(
    ("request_kwargs", "message"),
    [
        ({"owner": "project", "user_id": "alice"}, "unsupported reindex owner"),
        ({"owner": "memory"}, "user_id is required"),
        ({"owner": "knowledge_base", "tenant_id": "default"}, "kb_id is required"),
        ({"owner": "memory", "user_id": "alice", "mode": "append"}, "unsupported reindex mode"),
    ],
)
def test_reindex_request_validation_fails_fast(request_kwargs, message):
    from fleetent.vector_store import ReindexRequest, reindex

    with pytest.raises(ValueError, match=message):
        reindex(ReindexRequest(**request_kwargs))


def test_reindex_memory_dry_run_scans_without_vector_writes(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    writes: list[tuple[str, object]] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [
            IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-2", content="two", namespace=f"mem:{user_id}"),
        ],
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "clear_namespace",
        lambda namespace: writes.append(("clear", namespace)),
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: writes.append(("upsert", item_id)),
    )

    summary = reindex(ReindexRequest(owner="memory", user_id="alice", dry_run=True))

    assert summary.owner == "memory"
    assert summary.namespace == "mem:alice"
    assert summary.dry_run is True
    assert summary.scanned == 2
    assert summary.reindexed == 0
    assert summary.skipped == 2
    assert summary.failed == 0
    assert writes == []


def test_reindex_knowledge_base_dry_run_scans_without_vector_writes(monkeypatch):
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    writes: list[tuple[str, object]] = []
    monkeypatch.setattr(
        reindex_module.knowledge_base,
        "iter_indexable_knowledge_chunks",
        lambda tenant_id, kb_id: [
            IndexableItem(id="chunk-1", content="one", namespace=f"kb:{tenant_id}:{kb_id}")
        ],
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "clear_namespace",
        lambda namespace: writes.append(("clear", namespace)),
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: writes.append(("upsert", item_id)),
    )

    summary = reindex(
        ReindexRequest(
            owner="knowledge_base",
            tenant_id="tenant-a",
            kb_id="global",
            dry_run=True,
        )
    )

    assert summary.owner == "knowledge_base"
    assert summary.namespace == "kb:tenant-a:global"
    assert summary.dry_run is True
    assert summary.scanned == 1
    assert summary.reindexed == 0
    assert summary.skipped == 1
    assert summary.failed == 0
    assert writes == []


def test_reindex_memory_rebuild_clears_namespace_before_upserts(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [
            IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-2", content="two", namespace=f"mem:{user_id}"),
        ],
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "clear_namespace",
        lambda namespace: calls.append(("clear", namespace)),
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: calls.append(("upsert", item_id)),
    )

    summary = reindex(ReindexRequest(owner="memory", user_id="alice"))

    assert calls == [
        ("clear", "mem:alice"),
        ("upsert", "mem-1"),
        ("upsert", "mem-2"),
    ]
    assert summary.scanned == 2
    assert summary.reindexed == 2
    assert summary.skipped == 0
    assert summary.failed == 0


def test_reindex_memory_rebuild_upserts_each_item_with_content_and_namespace(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    upserts: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [
            IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-2", content="two", namespace=f"mem:{user_id}"),
        ],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: upserts.append((item_id, content, namespace)),
    )

    reindex(ReindexRequest(owner="memory", user_id="alice"))

    assert upserts == [
        ("mem-1", "one", "mem:alice"),
        ("mem-2", "two", "mem:alice"),
    ]


def test_reindex_memory_rebuild_continues_after_item_failure(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    upserts: list[str] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [
            IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-bad", content="bad", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-2", content="two", namespace=f"mem:{user_id}"),
        ],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(reindex_module, "_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(reindex_module, "_sleep", lambda seconds: None)

    def upsert(item_id: str, content: str, namespace: str) -> None:
        upserts.append(item_id)
        if item_id == "mem-bad":
            raise RuntimeError("boom")

    monkeypatch.setattr(reindex_module.runtime, "upsert", upsert)

    summary = reindex(ReindexRequest(owner="memory", user_id="alice"))

    assert upserts == ["mem-1", "mem-bad", "mem-bad", "mem-bad", "mem-bad", "mem-2"]
    assert summary.scanned == 3
    assert summary.reindexed == 2
    assert summary.skipped == 0
    assert summary.failed == 1


def test_reindex_retries_transient_item_failure(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    calls: list[str] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}")],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(reindex_module, "_BACKOFF_SECONDS", (0.0,))
    monkeypatch.setattr(reindex_module, "_sleep", lambda seconds: None)

    def upsert(item_id: str, content: str, namespace: str) -> None:
        calls.append(item_id)
        if len(calls) == 1:
            raise RuntimeError("provider returned status 429")

    monkeypatch.setattr(reindex_module.runtime, "upsert", upsert)

    summary = reindex(ReindexRequest(owner="memory", user_id="alice"))

    assert calls == ["mem-1", "mem-1"]
    assert summary.reindexed == 1
    assert summary.failed == 0


def test_reindex_applies_injectable_pacing_between_items(monkeypatch):
    from fleetent import memory
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    sleeps: list[float] = []
    monkeypatch.setattr(
        memory,
        "iter_indexable_memories",
        lambda user_id: [
            IndexableItem(id="mem-1", content="one", namespace=f"mem:{user_id}"),
            IndexableItem(id="mem-2", content="two", namespace=f"mem:{user_id}"),
        ],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(reindex_module.runtime, "upsert", lambda *args: None)
    monkeypatch.setattr(reindex_module, "_PACING_SECONDS", 0.25)
    monkeypatch.setattr(reindex_module, "_sleep", lambda seconds: sleeps.append(seconds))

    summary = reindex(ReindexRequest(owner="memory", user_id="alice"))

    assert sleeps == [0.25, 0.25]
    assert summary.reindexed == 2
    assert summary.failed == 0


def test_reindex_knowledge_base_rebuild_clears_namespace_before_upserts(monkeypatch):
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        reindex_module.knowledge_base,
        "iter_indexable_knowledge_chunks",
        lambda tenant_id, kb_id: [
            IndexableItem(id="chunk-1", content="one", namespace=f"kb:{tenant_id}:{kb_id}"),
            IndexableItem(id="chunk-2", content="two", namespace=f"kb:{tenant_id}:{kb_id}"),
        ],
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "clear_namespace",
        lambda namespace: calls.append(("clear", namespace)),
    )
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: calls.append(("upsert", item_id)),
    )

    summary = reindex(ReindexRequest(owner="knowledge_base", tenant_id="tenant-a", kb_id="global"))

    assert calls == [
        ("clear", "kb:tenant-a:global"),
        ("upsert", "chunk-1"),
        ("upsert", "chunk-2"),
    ]
    assert summary.scanned == 2
    assert summary.reindexed == 2
    assert summary.skipped == 0
    assert summary.failed == 0


def test_reindex_knowledge_base_rebuild_upserts_each_chunk_content_and_namespace(monkeypatch):
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    upserts: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        reindex_module.knowledge_base,
        "iter_indexable_knowledge_chunks",
        lambda tenant_id, kb_id: [
            IndexableItem(id="chunk-1", content="one", namespace=f"kb:{tenant_id}:{kb_id}"),
            IndexableItem(id="chunk-2", content="two", namespace=f"kb:{tenant_id}:{kb_id}"),
        ],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(
        reindex_module.runtime,
        "upsert",
        lambda item_id, content, namespace: upserts.append((item_id, content, namespace)),
    )

    reindex(ReindexRequest(owner="knowledge_base", tenant_id="tenant-a", kb_id="global"))

    assert upserts == [
        ("chunk-1", "one", "kb:tenant-a:global"),
        ("chunk-2", "two", "kb:tenant-a:global"),
    ]


def test_reindex_knowledge_base_rebuild_continues_after_chunk_failure(monkeypatch):
    from fleetent.vector_store import IndexableItem, ReindexRequest, reindex

    reindex_module = importlib.import_module("fleetent.vector_store.reindex")
    upserts: list[str] = []
    monkeypatch.setattr(
        reindex_module.knowledge_base,
        "iter_indexable_knowledge_chunks",
        lambda tenant_id, kb_id: [
            IndexableItem(id="chunk-1", content="one", namespace=f"kb:{tenant_id}:{kb_id}"),
            IndexableItem(id="chunk-bad", content="bad", namespace=f"kb:{tenant_id}:{kb_id}"),
            IndexableItem(id="chunk-2", content="two", namespace=f"kb:{tenant_id}:{kb_id}"),
        ],
    )
    monkeypatch.setattr(reindex_module.runtime, "clear_namespace", lambda namespace: None)
    monkeypatch.setattr(reindex_module, "_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(reindex_module, "_sleep", lambda seconds: None)

    def upsert(item_id: str, content: str, namespace: str) -> None:
        upserts.append(item_id)
        if item_id == "chunk-bad":
            raise RuntimeError("boom")

    monkeypatch.setattr(reindex_module.runtime, "upsert", upsert)

    summary = reindex(ReindexRequest(owner="knowledge_base", tenant_id="tenant-a", kb_id="global"))

    assert upserts == [
        "chunk-1",
        "chunk-bad",
        "chunk-bad",
        "chunk-bad",
        "chunk-bad",
        "chunk-2",
    ]
    assert summary.scanned == 3
    assert summary.reindexed == 2
    assert summary.skipped == 0
    assert summary.failed == 1
