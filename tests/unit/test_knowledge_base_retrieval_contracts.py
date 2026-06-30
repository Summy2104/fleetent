import inspect
from contextlib import suppress
from types import SimpleNamespace

import pytest


def _chunk(chunk_id: str, score: float = 0.5):
    from fleetent.knowledge_base.models import KnowledgeChunk

    return KnowledgeChunk(
        id=chunk_id,
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="kb-1",
        filename="guide.md",
        content=f"chunk:{chunk_id}",
        position=0,
        score=score,
        source="upload",
        source_url=None,
    )


class _FakeStore:
    def __init__(self, keyword_results=None) -> None:
        self.keyword_results = list(keyword_results or [])
        self.keyword_calls: list[tuple[str, str, list[str], int]] = []
        self.embedding_identity: tuple[str, int] | None = None
        self.chunks_by_id: dict[str, object] = {}

    def get_embedding_identity(self, tenant_id: str, kb_id: str) -> tuple[str, int] | None:
        return self.embedding_identity

    def search_keyword(
        self, query: str, tenant_id: str, kb_ids: list[str], limit: int
    ):  # pragma: no cover - exercised in async tests
        self.keyword_calls.append((query, tenant_id, kb_ids, limit))
        return list(self.keyword_results)

    def get_chunks_by_ids(self, tenant_id: str, chunk_ids: list[str]):
        return [
            self.chunks_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in self.chunks_by_id
        ]


def _monotonic(values: list[float]):
    last = values[-1]
    remaining = iter(values)

    def _fake() -> float:
        nonlocal last
        with suppress(StopIteration):
            last = next(remaining)
        return last

    return _fake


def test_retrieval_search_functions_accept_readable_store() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, search

    search_sig = inspect.signature(search.search)
    graph_sig = inspect.signature(graph_search.graph_search)
    assert "KnowledgeReadable" in str(search_sig.parameters["store"].annotation)
    assert "KnowledgeReadable" in str(graph_sig.parameters["store"].annotation)


def test_dead_agent_kb_binding_symbols_are_not_exported() -> None:
    import fleetent.knowledge_base as knowledge_base
    import fleetent.knowledge_base.retrieval as retrieval

    resolver_name = "resolve_agent_kb_ids"
    for module, name in (
        (knowledge_base, "AgentKnowledgeBaseBinding"),
        (knowledge_base, "list_agent_kb_bindings"),
        (knowledge_base, resolver_name),
        (retrieval, "AgentKnowledgeBaseBinding"),
        (retrieval, resolver_name),
        (retrieval, "scope"),
    ):
        with pytest.raises(AttributeError):
            getattr(module, name)


def test_retrieval_modules_do_not_reference_writes() -> None:
    from fleetent.knowledge_base.retrieval import graph_search, search

    for module in (graph_search, search):
        source = inspect.getsource(module)
        assert "insert_document(" not in source
        assert "insert_chunks(" not in source
        assert "update_knowledge_base_description(" not in source
        assert "archive_knowledge_base(" not in source
        assert "delete_document(" not in source
        assert "delete_scoped_document(" not in source


def test_long_term_ctx_does_not_reference_agent_kbs_management_store() -> None:
    import fleetent.long_term_ctx as long_term_ctx

    source = inspect.getsource(long_term_ctx)
    assert "agent_kbs_store" not in source
    assert "platform.knowledge_base_management" not in source


@pytest.mark.parametrize(
    ("mode", "rerank", "expected_ids"),
    [
        ("vector", False, ["vec-1", "vec-2"]),
        ("keyword", False, ["kw-1", "kw-2"]),
        ("hybrid", False, ["hy-1", "hy-2"]),
        ("hybrid", True, ["rr-1", "rr-2"]),
    ],
)
async def test_search_records_kb_retrieval_for_all_modes(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    rerank: bool,
    expected_ids: list[str],
) -> None:
    from fleetent.knowledge_base.retrieval import search as search_module
    from fleetent.observability import KBRetrievalAuditContext

    captured: list[dict[str, object]] = []
    keyword_results = [_chunk("kw-1", 0.7), _chunk("kw-2", 0.2)] if mode == "keyword" else []
    store = _FakeStore(keyword_results=keyword_results)

    async def _fake_vector(*_args, **_kwargs):
        return [_chunk("vec-1", 0.9), _chunk("vec-2", 0.4)]

    async def _fake_hybrid(_query, _tenant_id, _kb_ids, _limit, _store, *, rerank=False):
        return (
            [_chunk("rr-1", 0.95), _chunk("rr-2", 0.6)]
            if rerank
            else [_chunk("hy-1", 0.8), _chunk("hy-2", 0.3)]
        )

    monkeypatch.setattr(search_module.time, "monotonic", _monotonic([10.0, 10.025]))
    monkeypatch.setattr(search_module, "_search_vector", _fake_vector)
    monkeypatch.setattr(search_module, "_search_hybrid", _fake_hybrid)
    monkeypatch.setattr(
        search_module,
        "record_kb_retrieval",
        lambda context, **kwargs: captured.append({"context": context, **kwargs}),
    )

    results = await search_module.search(
        "reset password",
        store=store,
        tenant_id="tenant-a",
        kb_ids=["kb-1", "kb-2"],
        limit=2,
        mode=mode,
        rerank=rerank,
        audit_context=KBRetrievalAuditContext(
            run_id="run-1",
            session_id="sess-1",
            user_id="user-1",
            agent_name="agent-1",
            tenant_id="tenant-a",
        ),
    )

    assert [chunk.id for chunk in results] == expected_ids
    assert len(captured) == 1
    payload = captured[0]
    assert payload["mode"] == mode
    assert payload["latency_ms"] == pytest.approx(25.0)
    assert payload["kb_ids"] == ["kb-1", "kb-2"]
    assert payload["query"] == "reset password"
    assert [chunk.id for chunk in payload["results"]] == expected_ids
    assert payload["context"] == KBRetrievalAuditContext(
        run_id="run-1",
        session_id="sess-1",
        user_id="user-1",
        agent_name="agent-1",
        tenant_id="tenant-a",
    )


async def test_search_records_empty_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import search as search_module
    from fleetent.observability import KBRetrievalAuditContext

    captured: list[dict[str, object]] = []

    async def _fake_vector(*_args, **_kwargs):
        return []

    monkeypatch.setattr(search_module.time, "monotonic", _monotonic([20.0, 20.004]))
    monkeypatch.setattr(search_module, "_search_vector", _fake_vector)
    monkeypatch.setattr(
        search_module,
        "record_kb_retrieval",
        lambda context, **kwargs: captured.append({"context": context, **kwargs}),
    )

    results = await search_module.search(
        "missing",
        store=_FakeStore(),
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        mode="vector",
        audit_context=KBRetrievalAuditContext(run_id="run-2", tenant_id="tenant-a"),
    )

    assert results == []
    assert len(captured) == 1
    assert captured[0]["results"] == []


async def test_long_term_ctx_search_knowledge_uses_single_validated_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.agent_config as agent_config
    from fleetent import long_term_ctx

    captured: dict[str, object] = {}

    async def _fake_search(query: str, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return []

    class _Bindings:
        def __iter__(self):
            return iter(
                [
                    SimpleNamespace(
                        tenant_id="tenant-a",
                        kb_id="kb-1",
                        permissions=SimpleNamespace(search=True),
                    ),
                    SimpleNamespace(
                        tenant_id="tenant-b",
                        kb_id="kb-2",
                        permissions=SimpleNamespace(search=True),
                    ),
                ]
            )

    agent = SimpleNamespace(
        knowledge=SimpleNamespace(
            enabled=True,
            tenant_id="tenant-z",
            bindings=_Bindings(),
            retrieval_policy=SimpleNamespace(mode="hybrid"),
        )
    )

    monkeypatch.setattr(agent_config, "active_agent_or_default", lambda: agent)
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", _fake_search)

    results = await long_term_ctx._search_knowledge("u1", "reset password", "agent-1", 3)

    assert results == []
    assert captured == {
        "query": "reset password",
        "tenant_id": "tenant-z",
        "kb_ids": ["kb-1", "kb-2"],
        "limit": 3,
        "mode": "hybrid",
        "audit_context": None,
    }


async def test_search_swallows_audit_helper_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import search as search_module
    from fleetent.observability import KBRetrievalAuditContext

    expected = [_chunk("vec-1", 0.9)]

    async def _fake_vector(*_args, **_kwargs):
        return expected

    monkeypatch.setattr(search_module, "_search_vector", _fake_vector)
    monkeypatch.setattr(
        search_module,
        "record_kb_retrieval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit down")),
    )

    results = await search_module.search(
        "query",
        store=_FakeStore(),
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        mode="vector",
        audit_context=KBRetrievalAuditContext(run_id="run-3", tenant_id="tenant-a"),
    )

    assert results == expected


async def test_search_uses_plaintext_audit_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import search as search_module
    from fleetent.observability import KBRetrievalAuditContext

    captured: list[dict[str, object]] = []

    async def _fake_vector(*_args, **_kwargs):
        return [_chunk("vec-1", 0.9)]

    monkeypatch.setattr(search_module, "_search_vector", _fake_vector)
    monkeypatch.setattr(
        search_module,
        "record_kb_retrieval",
        lambda context, **kwargs: captured.append({"context": context, **kwargs}),
    )
    monkeypatch.setattr(
        search_module.agent_config,
        "active_agent_or_default",
        lambda: SimpleNamespace(
            knowledge=SimpleNamespace(
                retrieval_audit=SimpleNamespace(plaintext=True),
            )
        ),
    )

    await search_module.search(
        "query",
        store=_FakeStore(),
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        mode="vector",
        audit_context=KBRetrievalAuditContext(run_id="run-9", tenant_id="tenant-a"),
    )

    assert captured[0]["plaintext"] is True


async def test_search_fails_when_current_embedding_identity_mismatches_kb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.knowledge_base.retrieval import search as search_module
    from fleetent.vector_store import EmbeddingIdentity

    store = _FakeStore()
    store.embedding_identity = ("bge-small", 384)
    monkeypatch.setattr(
        search_module.vector_store,
        "current_embedding_identity",
        lambda: EmbeddingIdentity(model="nomic-embed", dimensions=768),
    )

    with pytest.raises(Exception, match="Knowledge base embedding mismatch"):
        await search_module.search(
            "query",
            store=store,
            tenant_id="tenant-a",
            kb_ids=["kb-1"],
            mode="vector",
        )
