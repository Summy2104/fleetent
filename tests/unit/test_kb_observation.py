from datetime import UTC, datetime

from fleetent.observability.traces import TraceEvent
from fleetent.platform.knowledge_base_management import kb_observation


def _event(
    *,
    agent_name: str,
    session_id: str,
    latency_ms: float,
    hit_count: int,
    scores: list[float],
    kb_ids: list[str],
) -> TraceEvent:
    return TraceEvent(
        run_id=f"run-{session_id}",
        event_type="kb_retrieval",
        payload={
            "latency_ms": latency_ms,
            "hit_count": hit_count,
            "scores": scores,
            "kb_ids": kb_ids,
        },
        agent_name=agent_name,
        session_id=session_id,
        ts=datetime(2026, 6, 22, 10, 0, tzinfo=UTC),
    )


def test_aggregate_computes_proxy_metrics_across_bound_agents(monkeypatch) -> None:
    events_by_agent = {
        "ops-a": [
            _event(
                agent_name="ops-a",
                session_id="s-1",
                latency_ms=10.0,
                hit_count=2,
                scores=[0.9, 0.6],
                kb_ids=["sales"],
            ),
            _event(
                agent_name="ops-a",
                session_id="s-2",
                latency_ms=20.0,
                hit_count=0,
                scores=[],
                kb_ids=["sales"],
            ),
        ],
        "ops-b": [
            _event(
                agent_name="ops-b",
                session_id="s-3",
                latency_ms=40.0,
                hit_count=1,
                scores=[0.4],
                kb_ids=["sales", "support"],
            ),
            _event(
                agent_name="ops-b",
                session_id="s-x",
                latency_ms=80.0,
                hit_count=3,
                scores=[0.7, 0.5, 0.3],
                kb_ids=["finance"],
            ),
        ],
    }

    monkeypatch.setattr(
        kb_observation.agent_store,
        "get_agent_name_by_id",
        lambda agent_id: {7: "ops-a", 8: "ops-b", 9: None}[agent_id],
    )
    monkeypatch.setattr(
        kb_observation,
        "query_trace_events",
        lambda query: iter(events_by_agent.get(str(query.agent_name), [])),
    )

    aggregate = kb_observation.aggregate("default", "sales", [7, 8, 9])

    assert aggregate["kb_id"] == "sales"
    assert aggregate["bound_agents"] == [7, 8]
    assert aggregate["query_count"] == 3
    assert aggregate["hit_count"] == 3
    assert aggregate["zero_recall_rate"] == 1 / 3
    assert aggregate["latency_ms"] == {"p50": 20.0, "p95": 40.0}
    assert aggregate["score_distribution"] == {
        "count": 3,
        "min": 0.4,
        "p50": 0.6,
        "p95": 0.9,
        "max": 0.9,
    }
    assert aggregate["sessions"] == ["s-1", "s-2", "s-3"]
