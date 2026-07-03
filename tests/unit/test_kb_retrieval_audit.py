import hashlib

from fleetent.knowledge_base.models import KnowledgeChunk


def _chunk(chunk_id: str, score: float = 0.5) -> KnowledgeChunk:
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


def test_record_kb_retrieval_builds_trace_event_without_plaintext(monkeypatch) -> None:
    from fleetent.observability import traces

    captured: list[traces.TraceEvent] = []
    monkeypatch.setattr(traces, "record_trace_event", captured.append)

    traces.record_kb_retrieval(
        traces.KBRetrievalAuditContext(
            run_id="run-1",
            session_id="sess-1",
            user_id="user-1",
            agent_name="agent-1",
            tenant_id="tenant-a",
        ),
        query="reset postgres password",
        results=[_chunk("c2", 0.9), _chunk("c1", 0.3)],
        latency_ms=12.7,
        mode="hybrid",
        kb_ids=["kb-1", "kb-2"],
    )

    assert len(captured) == 1
    event = captured[0]
    assert event.event_type == "kb_retrieval"
    assert event.run_id == "run-1"
    assert event.session_id == "sess-1"
    assert event.user_id == "user-1"
    assert event.agent_name == "agent-1"
    assert event.tenant_id == "tenant-a"
    assert event.payload == {
        "result_ids": ["c2", "c1"],
        "scores": [0.9, 0.3],
        "hit_count": 2,
        "latency_ms": 12.7,
        "mode": "hybrid",
        "kb_ids": ["kb-1", "kb-2"],
        "query_hash": hashlib.sha256(b"reset postgres password").hexdigest(),
    }
    assert "raw_query" not in event.payload
    assert "raw_chunks" not in event.payload


def test_record_kb_retrieval_swallows_write_failures(monkeypatch) -> None:
    from fleetent.observability import traces

    warnings: list[tuple[str, dict[str, object]]] = []

    class _FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            warnings.append((message, fields))

    def _boom(_event: traces.TraceEvent) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(traces, "_logger", _FakeLogger())
    monkeypatch.setattr(traces, "record_trace_event", _boom)

    traces.record_kb_retrieval(
        traces.KBRetrievalAuditContext(run_id="run-2", tenant_id="tenant-a"),
        query="why is deploy red",
        results=[_chunk("c9", 0.4)],
        latency_ms=3.5,
        mode="vector",
        kb_ids=["kb-1"],
    )

    assert len(warnings) == 1
    message, fields = warnings[0]
    assert message == "kb_retrieval_trace_record_failed"
    assert fields["run_id"] == "run-2"
    assert isinstance(fields["exception"], RuntimeError)
    assert str(fields["exception"]) == "db down"


def test_record_kb_retrieval_includes_plaintext_when_enabled(monkeypatch) -> None:
    from fleetent.observability import traces

    captured: list[traces.TraceEvent] = []
    monkeypatch.setattr(traces, "record_trace_event", captured.append)

    traces.record_kb_retrieval(
        traces.KBRetrievalAuditContext(run_id="run-3", tenant_id="tenant-a"),
        query="show me the raw chunk",
        results=[_chunk("c5", 0.8)],
        latency_ms=9.0,
        mode="graph",
        kb_ids=["kb-9"],
        plaintext=True,
    )

    assert captured[0].payload["raw_query"] == "show me the raw chunk"
    assert captured[0].payload["raw_chunks"] == [{"id": "c5", "content": "chunk:c5"}]
